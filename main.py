#!/usr/bin/python2
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from xml.etree.ElementTree import Element

import os
import re
import time
import glob
import logging
import subprocess


# TODO implement argparse arguments.

BACKUP_DIR = os.path.abspath('/media/andrew/Trancend/backup')
WILDCARD = '*'
CHECKPOINT_FILE = os.path.relpath('backup.chkpnt', BACKUP_DIR)
TIME_LIMIT_H = 1
TIME_LIMIT_S = TIME_LIMIT_H*3600

# Configuring logging object
LOGGER = logging.getLogger('vm-backup')
LOGGER.setLevel(logging.INFO)
LSH = logging.StreamHandler()
LSH.setLevel(logging.INFO)
FORMATTER = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s| %(message)s')
LSH.setFormatter(FORMATTER)
LOGGER.addHandler(LSH)

def get_block_devs(vm_name):
    """
    Finds all block disk memory objects for the vm.
    Will ignore raw-type disks which don't support snapshotting.
    """
    block_dev_cmd = ['virsh', 'domblklist', vm_name]
    block_dev_prc = subprocess.Popen(block_dev_cmd, stdout=subprocess.PIPE)
    devs = []
    results = (block_dev_prc.communicate()[0]).split('\n')
    for sect in results:
        if sect.endswith('qcow2'):
            devs.append(sect.split()[0])
        LOGGER.info('Found block device {}'.format(sect))
    return devs

def save_vm_state(vm_name):
    """
    Saves the VM Memory state, which requires quick suspend of
    the VM.
    """
    save_cmd = ['virsh',
                'save',
                vm_name,
                (os.path.join(BACKUP_DIR, vm_name+'-memory')),
                '--running'
               ]
    save_prc = subprocess.Popen(save_cmd)
    save_prc.communicate()

    LOGGER.info('Backup of vm {} state successful'.format(vm_name))

def dump_vm_info(vm_name):
    """
    Saves the VM configuration XML files.
    """
    dump_name = os.path.join(BACKUP_DIR, '{}.xml'.format(vm_name))
    LOGGER.info('Dumping config for {} to {}'.format(vm_name, dump_name))
    save_cmd = ['virsh',
                'dumpxml',
                '--security-info',
                vm_name,
                '>',
                dump_name
               ]
    save_prc = subprocess.Popen(save_cmd)
    save_prc.communicate()
    

def undefine_vm(vm_name):
    """Makes the VM transient"""
    LOGGER.info('Destroying VM definitiion for VM {}'.format(vm_name))
    cmd = ['virsh', 'undefine', vm_name]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def suspend_vm(vm_name):
    """Suspends the VM"""
    LOGGER.info('Suspending VM {}'.format(vm_name))
    cmd = ['virsh', 'suspend', vm_name]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def restore_vm_state(vm_name):
    """Restores the VM. Necessary because save-state will stop the VM."""
    LOGGER.info('Restoring VM {}'.format(vm_name))
    cmd = ['virsh',
           'restore',
           (os.path.join(BACKUP_DIR, vm_name+'-memory')),
           '--running'
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def restore_vm_def(vm_name):
    """Restores the VM XML Configuration and defninition.."""
    LOGGER.info('Restoring VM definition for VM {}'.format(vm_name))
    cmd = ['virsh',
           'define',
           (os.path.join(BACKUP_DIR, vm_name+'.xml'))
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def safe_exit():
    pass

def copy_block(vm_name, disk_name):
    """Copies the block device into backup."""
    backup_name = os.path.join(BACKUP_DIR,
                               '{}-{}-backup.qcow2'.format(vm_name,
                                                           disk_name
                                                          )
                              )
    LOGGER.info('Copying disk {}, for vm {} into file {}...'.format(disk_name,
                                                                    vm_name,
                                                                    backup_name
                                                                   )
               )
    block_copy_cmd = ['virsh', 'blockcopy', vm_name, disk_name, backup_name]
    subprocess.Popen(block_copy_cmd)

    progress = 0
    progress_cmd = ['virsh', 'blockjob', vm_name, disk_name]

    while progress < 100:
        progress_prc = subprocess.Popen(progress_cmd, stdout=subprocess.PIPE)
        progress_report, _ = progress_prc.communicate()
        match = re.search(r'([0-9]{1,3})', progress_report)
        if not match:
            LOGGER.info("BlockJob aborted. Disk full?")
            safe_exit()
        progress = int(match.group(0))
        LOGGER.info('Copying... {} %'.format(progress))
        time.sleep(5)

def get_backup_name(vm_name, bk_id):
    """Composes the backup name."""
    return os.path.join(BACKUP_DIR, vm_name, 'backup-{}'.format(bk_id))

def check_disk_space(vm_name):
    """Checks to see if the required disk space is free on the destination
    volume"""
    LOGGER.info('Checking required disk space.')
    vm_req_space = 0
    disk_cmd = ['df', BACKUP_DIR]

def do_backup(vm_name):
    """Runs backup code from ported script (original: https://goo.gl/SVCiq9)"""
    LOGGER.info('Backing up {}'.format(vm_name))
    for i in range(2):
        LOGGER.info('Progress... {}%'.format(50 * (i + 1)))
        time.sleep(0.5)

def parse_list(vm_list):
    """Uses the format specification at https://goo.gl/p8F6Jv to get
    the list of guest VMs accessable by the machine."""
    vm_list = vm_list.split('\n')
    out_vms = []
    for row in vm_list[2:]:
        if not row:
            continue
        name = row.split()[1]
        out_vms.append(name)
    return out_vms

def get_existing_vms(allow_inactive=False):
    """This function uses virsh to list all vms and parses the output"""
    virsh_list = ['virsh', 'list']
    if allow_inactive:
        virsh_list += ['-all']
    list_prc = subprocess.Popen(virsh_list, stdout=subprocess.PIPE)
    vm_list = list_prc.communicate()[0] # Format specified at https://goo.gl/p8F6Jv
    vm_list = parse_list(vm_list)
    return vm_list

def main():
    # Get absolute path to all vm files in the given working directory
    existing_vm = get_existing_vms()
    existing_vm = set(map(os.path.abspath, existing_vm))
    LOGGER.info('{} VMs found.'.format(len(existing_vm)))

    # all_vm contains existing VMs and possibly removed backed up VMs
    all_vm = existing_vm

    backed_up = set()
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as openfile:
            backed_up = openfile.readlines()
            backed_up = set([vm.strip() for vm in backed_up])

        # Some VMs might be removed since the last run
        removed_vm = backed_up.difference(all_vm)
        # Add backed-up-and-removed VMs to all_vm for accurate counts of backups
        all_vm = all_vm.union(backed_up)
        
        if len(backed_up) < len(all_vm):
            if len(removed_vm) > 0:
                LOGGER.info('Checkpoint file found. {}/{} VMs were backed up.'
                            ' {} VMs were removed since last backup session.'
                            ' Continuing...'
                            .format(len(backed_up), len(all_vm), len(removed_vm)))
            else:
                LOGGER.info('Checkpoint file found. {}/{} VMs were backed up.'
                            ' Continuing...'.format(len(backed_up), len(all_vm)))
        else:
            LOGGER.info('Checkpoint file found. All VMs were backed up.'
                        ' Starting over...')
            os.remove(CHECKPOINT_FILE)
            backed_up = set()
            all_vm = existing_vm

    else:
        LOGGER.info('Checkpoint file not found. Starting from the beginning')
   
    start_time = time.time()
    timed_out = False
    backed_up_this_run = 0
    with open(CHECKPOINT_FILE, 'a') as openfile:
        for vm in all_vm:
            current_time = time.time()
            if current_time - start_time >= TIME_LIMIT_S:
                timed_out = True
                break
            if vm not in backed_up:
                do_backup(vm)
                backed_up.add(vm)
                backed_up_this_run += 1
                openfile.write(vm + '\n')

    if timed_out:
        LOGGER.info('Time limit reached')
    else:
        LOGGER.info('Finished backing up all VMs')
        os.remove(CHECKPOINT_FILE)
        LOGGER.info('Removed checkpoint file {}'.format(CHECKPOINT_FILE))

    LOGGER.info('Backed up VMs in this run: {}'.format(
        backed_up_this_run))
    LOGGER.info('Backed up VMs in total: {}/{}'.format(len(backed_up),
                                                       len(all_vm)))


if __name__ == '__main__':
    main()
