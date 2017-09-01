#!/usr/bin/python2
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import time
import glob
import logging
import subprocess

WORKING_DIR = Path('test')
WILDCARD = '*'
CHECKPOINT_FILE = Path('backup.chkpnt')
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
    block_dev_cmd = ['virsh', 'domblklist', vm_name]
    block_dev_prc = subprocess.Popen(block_dev_cmd, stdout=subprocess.PIPE)
    devs = []
    for sect in block_dev_prc.communicate()[0]:
        if sect.endswith('qcow2'):
            devs.append(sect)
    return devs
def do_backup(vm):
    """Runs backup code from ported script (original: https://goo.gl/SVCiq9)"""
    LOGGER.info('Backing up {}'.format(vm))
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
    xml_dmp = ['virsh', 'dumpxml']
    vl = subprocess.Popen(virsh_list, stdout=subprocess.PIPE)
    vm_list = vl.communicate()[0] # Format specified at https://goo.gl/p8F6Jv
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
            backed_up = f.readlines()
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
