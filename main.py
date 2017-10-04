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

BACKUP_DIR = os.path.abspath('/backup')
WILDCARD = '*'
CHECKPOINT_FILE = os.path.join(BACKUP_DIR,'backup.chkpnt')
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
    results = (block_dev_prc.communicate()[0]).splitlines()
    for sect in results:
        if sect.endswith('qcow2'):
            devs.append(sect.split()[0])
            print('Found block device {0}'.format(sect))
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

    print('Backup of vm {0} state successful'.format(vm_name))

def dump_vm_info(vm_name, backup_dir=BACKUP_DIR):
    """
    Saves the VM configuration XML files.
    """
    dump_name = os.path.join(backup_dir, '{one}.xml'.format(one=vm_name))
    print('Dumping config for {one} to {two}'.format(one=vm_name, two=dump_name))
    save_cmd = ['virsh',
                'dumpxml',
                '--security-info',
                vm_name
               ]
    with open(dump_name,'w+') as fout:
        save_prc = subprocess.Popen(save_cmd, stdout=fout)
        save_prc.communicate()
    

def undefine_vm(vm_name):
    """Makes the VM transient"""
    print('Destroying VM definitiion for VM {one}'.format(one=vm_name))
    cmd = ['virsh', 'undefine', vm_name]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def suspend_vm(vm_name):
    """Suspends the VM"""
    print('Suspending VM {0}'.format(vm_name))
    cmd = ['virsh', 'suspend', vm_name]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def restore_vm_state(vm_name, backup_dir=BACKUP_DIR):
    """Restores the VM. Necessary because save-state will stop the VM."""
    print('Restoring VM {one}'.format(one=vm_name))
    cmd = ['virsh',
           'restore',
           (os.path.join(backup_dir, vm_name+'-memory')),
           '--running'
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def restore_vm_def(vm_name, backup_dir=BACKUP_DIR):
    """Restores the VM XML Configuration and defninition.."""
    print('Restoring VM definition for VM {0}'.format(vm_name))
    cmd = ['virsh',
           'define',
           (os.path.join(backup_dir, vm_name+'.xml'))
          ]
    prc = subprocess.Popen(cmd)
    prc.communicate()

def safe_exit(vm_name):
    for d in get_block_devs(vm_name):
        prc = subprocess.Popen(['virsh', 'blockjob', vm_name, d, '--abort'])
        prc.communicate()

def copy_block(vm_name, disk_name, backup_dir=BACKUP_DIR):
    """Copies the block device into backup."""
    backup_name = os.path.join(backup_dir,
                               '{0}-{1}-backup.qcow2'.format(vm_name,
                                                           disk_name
                                                          )
                              )
    print('Copying disk {0}, for vm {1} into file {2}...'.format(disk_name,
                                                                    vm_name,
                                                                    backup_name
                                                                   )
               )
    block_copy_cmd = ['virsh', 'blockcopy', vm_name, disk_name, backup_name]
    prc = subprocess.Popen(block_copy_cmd)
    prc.communicate()

    progress = 0
    progress_cmd = ['virsh', 'blockjob', vm_name, disk_name]

    while progress < 100:
        progress_prc = subprocess.Popen(progress_cmd, stdout=subprocess.PIPE)
        progress_report, _ = progress_prc.communicate()
        if '[' not in progress_report:
            print("BlockJob aborted. Disk full?")
            safe_exit(vm_name)
            return
        else:
            progress = int(progress_report.split('[')[1].split()[0])
            print('Copying... {0} %'.format(progress))
        time.sleep(5)

def get_backup_name(vm_name, bk_id, backup_dir=BACKUP_DIR):
    """Composes the backup name."""
    return os.path.join(BACKUP_DIR, vm_name, 'backup-{0}'.format(bk_id))

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
        print (bk)
        if os.path.isdir(bk_prev) and os.path.isdir(bk):
            print('Remove old backup {0}'.format(bk_prev))
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
                print('Safely remove old backup directory.')
                cmd = ['rm',
                       '-rf',
                       os.path.join(BACKUP_DIR, vm_name, 'to-be-removed')]
                cmd_prc = subprocess.Popen(cmd)
                cmd_prc.communicate()
            else:
                print('Cannot remove old backup directory. Not a backup.')
                exit(1)
        if os.path.isdir(bk):
            print('Rename {0} to {1}'.format( bk, bk_prev))
            cmd = ['mv', bk, bk_prev]
            cmd_prc = subprocess.Popen(cmd)
            cmd_prc.communicate()
        
        bkcnt -= 1
    backup_dir = get_backup_name(vm_name, 0)
    prc = subprocess.Popen(['mkdir', '-p', backup_dir])
    prc.communicate()
    prc = subprocess.Popen(['chown', '-R', 'root:kvm', basepath])
    prc.communicate()
    return backup_dir


def check_disk_space(vm_name, blocks):
    """Checks to see if the required disk space is free on the destination
    volume"""
    print('Checking required disk space.')
    vm_req_space = 0
    disk_cmd = ['df', BACKUP_DIR]
    disk_prc = subprocess.Popen(disk_cmd, stdout=subprocess.PIPE)
    disk_out, _ = disk_prc.communicate()
    disk_space = int(disk_out.split()[9])

    for d in blocks:
        blk_space_cmd = ['virsh', 'domblkinfo', vm_name, d]
        blk_space_prc = subprocess.Popen(blk_space_cmd, stdout=subprocess.PIPE)
        blk_space_out, _ = blk_space_prc.communicate()
        req_space = int(blk_space_out.split()[-1]) / 1024 # In KiBytes
        print('Device {0} requires {1} KiB'.format(d, req_space))
        vm_req_space += req_space

    mem_size_cmd = ['virsh', 'dominfo', vm_name]
    mem_size_prc = subprocess.Popen(mem_size_cmd, stdout=subprocess.PIPE)
    mem_size_out, _ = mem_size_prc.communicate()
    mem = int(mem_size_out.split('\n')[7].split()[2])
    print('VM memory size is {0} KiB'.format(mem))
    mem = int(mem*1.2)
    print('VM memory requirement scaled to {0} KiB'.format(mem))
    vm_req_space += mem

    last_backup_cmd = ['du', '-s', get_last_backup_name(vm_name)]
    last_backup_prc = subprocess.Popen(last_backup_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    last_backup_out, _ = last_backup_prc.communicate()
    if not _:
        last_backup_size = int(last_backup_out.split()[0])
        vm_req_space -= last_backup_size

    mb_free = disk_space / 1024
    mb_required = vm_req_space / 1024

    if mb_free < mb_required:
        print('Cannot make backup; only {0} MiB available.'.format(mb_free) +
                    ' Minimum needed is {0} MiB.'.format(mb_required))
        return 1
    print(
        'Backup possible: {0} MiB expected to remain after backup'.format(
            mb_free-mb_required))
    return 0

def backup_vm(vm_name):
    """Runs backup process for a specified vm."""
    prc = subprocess.Popen(['mkdir', '-p', BACKUP_DIR])
    prc.communicate()
    prc = subprocess.Popen(['mkdir', '-p', os.path.join(BACKUP_DIR, vm_name)])
    prc.communicate()
    prc = subprocess.Popen(['chown', '-R', 'root:kvm', BACKUP_DIR])
    prc.communicate()

    # Starting Backup
    print('Backup of {0} started'.format(vm_name))
    blocks = get_block_devs(vm_name)
    result = check_disk_space(vm_name, blocks)
    if result:
        exit(1)
    
    backup_dir = rotate_backups(vm_name)
    dump_vm_info(vm_name, backup_dir)
    undefine_vm(vm_name)
    for d in blocks:
        copy_block(vm_name, d, backup_dir)
        subprocess.Popen(['virsh', 'blockjob', vm_name, d, '--abort'])
    suspend_vm(vm_name)
    save_vm_state(vm_name, backup_dir)
    restore_vm_state(vm_name, backup_dir)
    restore_vm_def(vm_name, backup_dir)

    print("Backup of {0} finished".format(vm_name))

def do_backup(vm_name):
    """Runs backup code from ported script (original: https://goo.gl/SVCiq9)"""
    # backup_vm(vm_name)

    prc = subprocess.Popen(['./kvm-backup.sh', vm_name])
    prc.communicate()

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
    print('{0} VMs found.'.format(len(existing_vm)))

    # all_vm contains existing VMs and possibly removed backed up VMs
    all_vm = set(existing_vm)

    backed_up = set()
    if os.path.isfile(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as openfile:
            backed_up = openfile.readlines()
            backed_up = set([vm.strip() for vm in backed_up])

        # Some VMs might be removed since the last run
        removed_vm = backed_up.difference(all_vm)
        # Add backed-up-and-removed VMs to all_vm for accurate counts of backups
        all_vm = all_vm.union(backed_up)
        
        if len(backed_up) < len(all_vm):
            if len(removed_vm) > 0:
                print('Checkpoint file found. {0}/{1} VMs were backed up.'
                            ' {2} VMs were removed since last backup session.'
                            ' Continuing...'
                            .format(len(backed_up), len(all_vm), len(removed_vm)))
            else:
                print('Checkpoint file found. {0}/{1} VMs were backed up.'
                            ' Continuing...'.format(len(backed_up), len(all_vm)))
        else:
            print('Checkpoint file found. All VMs were backed up.'
                        ' Starting over...')
            os.remove(CHECKPOINT_FILE)
            backed_up = set()
            all_vm = existing_vm

    else:
        print('Checkpoint file not found. Starting from the beginning')
   
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
        print('Time limit reached')
    else:
        print('Finished backing up all VMs')
        os.remove(CHECKPOINT_FILE)
        print('Removed checkpoint file {0}'.format(CHECKPOINT_FILE))

    print('Backed up VMs in this run: {0}'.format(
        backed_up_this_run))
    print('Backed up VMs in total: {0}/{1}'.format(len(backed_up),
                                                       len(all_vm)))


if __name__ == '__main__':
    main()
