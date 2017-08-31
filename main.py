from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import time
import glob
import logging

WORKING_DIR = os.path.abspath('test')
WILDCARD = '*'
CHECKPOINT_FILE = os.path.abspath('backup.chkpnt')
TIME_LIMIT_S = 10

# Configuring logging object
logger = logging.getLogger('vm-backup')
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
sh.setFormatter(formatter)
logger.addHandler(sh)


def do_backup(vm):
    logger.info('Backing up {}'.format(vm))
    for i in range(4):
        logger.info('Progress... {}%'.format(25 * (i + 1)))
        time.sleep(1)


def main():
    # Get absolute path to all vm files in the given working directory
    existing_vm = glob.glob(os.path.join(WORKING_DIR, WILDCARD))
    existing_vm = set(map(os.path.abspath, existing_vm))
    logger.info('{} VMs found in {}'.format(len(existing_vm), WORKING_DIR))

    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            backed_up = f.readlines()
            backed_up = set([vm.strip() for vm in backed_up])

        logger.info('Checkpoint file found. {}/{} VMs were backed up.'
                    ' Continuing...'.format(len(backed_up), len(existing_vm)))
    else:
        logger.info('Checkpoint file not found. Starting from the beginning')
        backed_up = set([])
    
    start_time = time.time()
    timed_out = False
    backed_up_this_run = 0
    with open(CHECKPOINT_FILE, 'a') as f:
        for vm in existing_vm:
            current_time = time.time()
            if current_time - start_time >= TIME_LIMIT_S:
                timed_out = True
                break
            if vm not in backed_up:
                do_backup(vm)
                backed_up.add(vm)
                backed_up_this_run += 1
                f.write(vm + '\n')

    if timed_out:
        logger.info('Time limit reached')
        logger.info('Backed up VMs in this run: {}'.format(
            backed_up_this_run))
    else:
        logger.info('Finished backing up all VMs')

    logger.info('Backed up VMs in total: {}/{}'.format(len(backed_up),
        len(existing_vm)))


if __name__ == '__main__':
    main()
