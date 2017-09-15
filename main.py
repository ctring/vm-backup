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

MAX_BACKUPS = 2 # Maximum history of backups saved. 2 Means current backup and
                # one previous.

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

def save_vm_state(vm_name, backup_dir=BACKUP_DIR):
    """
    Saves the VM Memory state, which requires quick suspend of
    the VM.
    """
    save_cmd = ['virsh',
                'save',
                vm_name,
                (os.path.join(backup_dir, vm_name+'-memory')),
                '--running'
               ]
    save_prc = subprocess.Popen(save_cmd)
    save_prc.communicate()

    LOGGER.info('Backup of vm {} state successful'.format(vm_name))

def dump_vm_info(vm_name, backup_dir=BACKUP_DIR):
    """
    Saves the VM configuration XML files.
    """
    dump_name = os.path.join(backup_dir, '{}.xml'.format(vm_name))
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

def restore_vm_state(vm_name, backup_dir=BACKUP_DIR):
    """Restores the VM. Necessary because save-state will stop the VM."""
    LOGGER.info('Restoring VM {}'.format(vm_name))
    cmd = ['virsh',
           'restore',
           (os.path.join(backup_dir, vm_name+'-memory')),
           '--running'
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def restore_vm_def(vm_name, backup_dir=BACKUP_DIR):
    """Restores the VM XML Configuration and defninition.."""
    LOGGER.info('Restoring VM definition for VM {}'.format(vm_name))
    cmd = ['virsh',
           'define',
           (os.path.join(backup_dir, vm_name+'.xml'))
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def safe_exit():
    pass

def copy_block(vm_name, disk_name, backup_dir=BACKUP_DIR):
    """Copies the block device into backup."""
    backup_name = os.path.join(backup_dir,
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

def get_backup_name(vm_name, bk_id, backup_dir=BACKUP_DIR):
    """Composes the backup name."""
    return os.path.join(BACKUP_DIR, vm_name, 'backup-{}'.format(bk_id))

def get_last_backup_name(vm_name):
    """Returns the backup name for the final backup index"""
    return get_backup_name(vm_name, MAX_BACKUPS - 1)

def rotate_backups(vm_name):
    """Rotates or deletes the last backup."""
    basepath = os.path.join(BACKUP_DIR, vm_name)
    older_backup = get_backup_name(vm_name, MAX_BACKUPS)
    bkcnt = MAX_BACKUPS -2

    while bkcnt > 0:
        prev = bkcnt+1
        bk_prev = get_backup_name(vm_name, prev)
        bk = get_backup_name(vm_name, bkcnt)
        if os.path.isdir(bk_prev) and os.path.isdir(bk):
            LOGGER.info('Remove old backup %s', bk_prev)
            cmd = ['mv',
                   bk_prev,
                   os.path.join(BACKUP_DIR, vm_name, 'to-be-removed')]
            cmd_prc = subprocess.Popen(cmd)
            cmd_prc.communicate()
            if os.path.isfile(
                    os.path.join(
                        BACKUP_DIR,
                        vm_name,
                        'to-be-removed',
                        vm_name+'.xml')):
                LOGGER.info('Safely remove old backup directory.')
                cmd = ['rm',
                       '-rf',
                       os.path.join(BACKUP_DIR, vm_name, 'to-be-removed')]
                cmd_prc = subprocess.Popen(cmd)
                cmd_prc.communicate()
            else:
                LOGGER.info('Cannot remove old backup directory. Not a backup.')
                exit(1)
        if os.path.isdir(bk):
            LOGGER.info('Rename %s to %s', bk, bk_prev)
            cmd = ['mv', bk, bk_prev]
            cmd_prc = subprocess.Popen(cmd)
            cmd_prc.communicate()
        
        bkcnt -= 1
    backup_dir = get_backup_name(vm_name, 0)
    os.mkdir(backup_dir)
    subprocess.Popen(['chown', '-R', 'libvirt-qemu:kvm', basepath])
    return backup_dir


def check_disk_space(vm_name):
    """Checks to see if the required disk space is free on the destination
    volume"""
    LOGGER.info('Checking required disk space.')
    vm_req_space = 0
    disk_cmd = ['df', BACKUP_DIR]
    disk_prc = subprocess.Popen(disk_cmd, stdout=subprocess.PIPE)
    disk_out, _ = disk_prc.communicate()
    disk_space = int(disk_out.split()[9])

    for d in get_block_devs(vm_name):
        blk_space_cmd = ['virsh', 'domblkinfo', vm_name, d]
        blk_space_prc = subprocess.Popen(blk_space_cmd, stdout=subprocess.PIPE)
        blk_space_out, _ = blk_space_prc.communicate()
        req_space = int(blk_space_out.split()[-1]) / 1024 # In KiBytes
        LOGGER.info('Device {} requires {} KiB'.format(d, req_space))
        vm_req_space += req_space

    mem_size_cmd = ['virsh', 'dominfo', vm_name]
    mem_size_prc = subprocess.Popen(mem_size_cmd, subprocess.PIPE)
    mem_size_out, _ = mem_size_prc.communicate()
    mem = int(mem_size_out.split('\n')[7].split(2))
    LOGGER.info('VM memory size is {} KiB'.format(mem))
    mem = int(mem*1.2)
    LOGGER.info('VM memory requirement scaled to {} KiB'.format(mem))
    vm_req_space += mem

    last_backup_cmd = ['du', '-s', get_last_backup_name(vm_name)]
    last_backup_prc = subprocess.Popen(last_backup_cmd, stdout=subprocess.PIPE)
    last_backup_out, _ = last_backup_prc.communicate()
    last_backup_size = int(last_backup_out.split()[0])
    vm_req_space -= last_backup_size

    mb_free = disk_space / 1024
    mb_required = vm_req_space / 1024

    if mb_free < mb_required:
        LOGGER.info('Cannot make backup; only {} MiB available.'.format(mb_free) +
                    ' Minimum needed is {} MiB.'.format(mb_required))
        return 1
    LOGGER.info(
        'Backup possible: {} MiB expected to remain after backup'.format(
            mb_free-mb_required))
    return 0

def backup_vm(vm_name):
    """Runs backup process for a specified vm."""
    subprocess.Popen(['mkdir', '-p', BACKUP_DIR])
    subprocess.Popen(['chown', '-R', 'libvirt-qemu:kvm', BACKUP_DIR])

    # Starting Backup
    LOGGER.info('Backup of %s started', vm_name)
    blocks = get_block_devs(vm_name)
    result = check_disk_space(vm_name)
    if result:
        exit(1)
    
    backup_dir = rotate_backups(vm_name)
    dump_vm_info(vm_name, backup_dir)
    undefine_vm(vm_name)
    for d in blocks:
        copy_block(vm_name, d, backup_dir)
    suspend_vm(vm_name)
    save_vm_state(vm_name, backup_dir)
    restore_vm_state(vm_name, backup_dir)
    restore_vm_def(vm_name, backup_dir)

    LOGGER.info("Backup of %s finished", vm_name)

def do_backup(vm_name):
    """Runs backup code from ported script (original: https://goo.gl/SVCiq9)"""
    backup_vm(vm_name)

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
