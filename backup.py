'''WPI VMs backing up script

This script backs up VMs in a specified time limit and picks up where it left
off in the next run. It should be scheduled as a cron job to automatically
perform backing up in fixed time frames.

Example usage:
    ./python backup.py test1/*.qcow2 test2/*.vdi 7200
        This command performs backing up all qcow2 files in test1 and vdi files
        in test2 and stops when all files are backed up or 2 hours elapse,
        whichever comes first. 

Help:
    ./python backup.py -h

Author:
    Cuong Nguyen (ctnguyendinh@wpi.edu)

'''
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import time
import glob
import logging
import argparse

# Configure logging object
logger = logging.getLogger('vm-backup')
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s| %(message)s')
sh.setFormatter(formatter)
logger.addHandler(sh)


def expand_targets(targets):
    vm = set()
    for t in targets:
        vm |= set(map(os.path.abspath, glob.glob(t)))
    return vm


def do_backup(vm):
    logger.info('Backing up %s', vm)
    for i in range(2):
        logger.info('Progress... %d%%', 50 * (i + 1))
        time.sleep(0.5)


def consolidate_existing_and_backedup_vm(existing_vm, checkpoint_file, start_over):
    # all_vm contains existing VMs and possibly removed backed up VMs
    all_vm = existing_vm

    if start_over:
        logger.info('Starting over...')
        return all_vm, set()

    backed_up = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            backed_up = f.readlines()
            backed_up = set([vm.strip() for vm in backed_up])

        # Some VMs might be removed since the last run
        removed_vm = backed_up.difference(all_vm)
        # Add backed-up-and-removed VMs to all_vm for accurate counts of backups
        all_vm = all_vm.union(backed_up)
       
        if len(backed_up) < len(all_vm):
            if len(removed_vm) > 0:
                logger.info('Checkpoint file found. %d/%d VMs were backed up '
                            '(%d VMs were removed since last backup session).'
                            ' Continuing...',
                            len(backed_up), len(all_vm), len(removed_vm))
            else:
                logger.info('Checkpoint file found. %d/%d VMs were backed up.'
                            ' Continuing...', len(backed_up), len(all_vm))
        else:
            logger.info('Checkpoint file found. All VMs were backed up.'
                        ' Starting over...')
            os.remove(checkpoint_file)
            backed_up = set()
            all_vm = existing_vm

    else:
        logger.info('Checkpoint file not found. Starting from the beginning...')

    return all_vm, backed_up


def main(targets, time_limit_s, checkpoint_file, start_over):
    existing_vm = expand_targets(targets)
    logger.info('Found %d VMs', len(existing_vm))

    all_vm, backed_up = consolidate_existing_and_backedup_vm(
        existing_vm, checkpoint_file, start_over)

    start_time = time.time()
    timed_out = False
    backed_up_this_run = 0
    with open(checkpoint_file, 'a') as f:
        for vm in all_vm:
            current_time = time.time()
            if current_time - start_time >= time_limit_s:
                timed_out = True
                break
            if vm not in backed_up:
                do_backup(vm)
                backed_up.add(vm)
                backed_up_this_run += 1
                f.write(vm + '\n')

    if timed_out:
        logger.info('Time limit reached')
    else:
        logger.info('Finished backing up all VMs')

    logger.info('Backed up VMs in this run: %d', backed_up_this_run)
    logger.info('Backed up VMs in total: %d/%d', len(backed_up), len(all_vm))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='This script backs up VMs in a specified time limit. '
                    'It picks up from where it left off in the next run.')
    parser.add_argument('targets', nargs='+',
                        help='one or more targets to be backed up. Unix-style '
                             'pattern matching is available')
    parser.add_argument('time_limit_s', type=int,
                        help='backing up process will only runs within this '
                             'time limit (in seconds)')
    parser.add_argument('-cf', default='backup.chkpnt',
                        help='name of checkpoint file (default: backup.chkpnt)')
    parser.add_argument('-s', action='store_true',
                        help='start the back up process from the beginning')

    args = parser.parse_args()
 
    main(targets=args.targets,
         time_limit_s=args.time_limit_s,
         checkpoint_file=args.cf,
         start_over=args.s)
