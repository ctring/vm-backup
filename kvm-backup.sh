#!/bin/bash
# A simple backup script for kvm
# Original source: http://soliton74.blogspot.no/2013/08/about-kvm-qcow2-live-backup.html
#
# Author: Luca Lazzeroni <luca.lazzeroni74@gmail.it>
# Web: http://soliton74.blogspot.it
#
# Patched by: Tim Miller Dyck
#
# Patched by: Runar Ingebrigtsen <runar@voit.no>
# Web: http://rin.no
#
####################################################
# This script is shared as-is. Do whatever you want.
####################################################

# Default base backup path -- this directory will be created if it does not already exist
BKPATH="/backup"

# String to match in list of VM block devices
VMDATAMATCH="qcow2"

# Maximum history of VM backups allowed (e.g. 2 means keep the current backup and one previous backup)
MAXBACKUP=2

# Default email (an empty string means no e-mail will be sent)
TARGET_EMAIL=""

# Default sender email
SENDER_NAME="VM Backup"
SENDER_EMAIL="vmbackup@voit.no"

########################################

LOGLINES=""

# logging function

function logLineLocal() {
  ORA=$(date +"%D %H:%M:%S")  
  echo "$ORA - $@"
}

function logLine() {
  ORA=$(date +"%D %H:%M:%S")  
  echo "$ORA - $@"
  LOGLINES+="$ORA - $@\n"
}

# if needed, send log via mail

function doExit() {
  # Compose message and send it
  if [ "x$TARGET_EMAIL" != "x" ]; then
    local MESSAGE="To: $TARGET_EMAIL\nSubject: "
    if [ $1 -eq 0 ]; then
      MESSAGE+="Backup ##OK##\n\n$LOGLINES\n"
    else
      MESSAGE+="Backup ##FAILED##\n\n$LOGLINES\n"
    fi
    echo -e $MESSAGE | sendmail -f$SENDER_EMAIL -F"$SENDER_NAME" $TARGET_EMAIL
  fi
  exit $1
}

# get domain info

function checkDomain() {
  local VMNAME=$1
  DOMINFO=$(virsh dominfo $VMNAME 2> /dev/null)
  if [ "x$DOMINFO" == "x" ]; then
    logLine "Cannot find domain $VMNAME"
    doExit 1
  fi
}

# get vm devices

function getVMBlockDevs() {
  local VMNAME=$1
  # Filter list of all block devices by VMDATAMATCH, and strip string to full path
  BLOCKDEVS=$(virsh domblklist $VMNAME 2> /dev/null | grep "$VMDATAMATCH" | sed -e 's/.* //')
  if [ "x$BLOCKDEVS" == "x" ]; then
    logLine "Cannot get block device list for domain. Exit."
    doExit 1
  fi
}

# abort block copy job
function abortCopy() {
  logLine "Cancel job for disk $2 on vm $1"
  virsh blockjob $1 $2 --abort 2> /dev/null
}

# abort all block copy jobs
function abortAllJobs() {
  logLine "Cancelling all block-copy jobs"
  for i in $BLOCKDEVS; do
    abortCopy $1 $i 2> /dev/null
  done
}

# save vm state (RAM) - this will power off the VM
function saveVMState() {
  local VMNAME=$1
  logLine "Saving VM memory for $VMNAME"
  logLine $(virsh save $VMNAME $BKPATH/$VMNAME-memory --running 2>&1)
}

# dump XML domain definition
function dumpVMdefinition() {
  local VMNAME=$1
  local DUMPNAME="$BKPATH/$VMNAME.xml"
  logLine "Dumping definition of $VMNAME to $DUMPNAME"
  virsh dumpxml --security-info $VMNAME > $DUMPNAME 2> /dev/null
  if [ $? -eq 1 ]; then
    logLine "VM $1 doesn't exists"
    doExit 1
  fi
}

# Make the VM transient
function undefineVM() {
  local VMNAME=$1
  logLine "Destroying vm definition for VM $VMNAME"
  logLine $(virsh undefine $VMNAME)
}

# Suspend the VM
function suspendVM() {
  local VMNAME=$1
  logLine "Suspending vm $VMNAME"
  logLine $(virsh suspend $VMNAME)
}

# restore VM state. this is necessary because the save-vm stop the vm 
function restoreVMState() {
  local VMNAME=$1
  logLine "Restoring vm $VMNAME"
  logLine $(virsh restore $BKPATH/$VMNAME-memory --running)
}

# restore VM definition
function defineVM() {
  local VMNAME=$1
  logLine "Restoring VM definition for vm $VMNAME"
  logLine $(virsh define $BKPATH/$VMNAME.xml)
}

function safeExit() {
  # exit recoverying vm
  local VMNAME=$1
  local MESSAGE=$2
  logLine $MESSAGE
  # abort all jobs
  abortAllJobs $VMNAME
  # re-define domain
  defineVM $VMNAME
  # exit
  logLine "Safe exit done."
  doExit 1
}

# start the blockcopy job
function copyBlock() {
  local VMNAME=$1
  local DISKNAME=$2
  local BAKNAME="$BKPATH/$VMNAME-$DISKNAME-backup.qcow2"
  logLine "Copying disk $DISKNAME for vm $VMNAME into file $BAKNAME..."
  virsh blockcopy $VMNAME $DISKNAME $BAKNAME #2> /dev/null
  if [ $? -gt 0 ]; then
    safeExit $VMNAME "Problem starting blockcopy"
  fi
  local PROGRESS=0
  until [ $PROGRESS -eq 100 ]; do
    PROGRESS=$(virsh blockjob $VMNAME $DISKNAME 2>&1 | egrep -o "([0-9]{1,3})")
    if [ "x$PROGRESS" == "x" ]; then
      safeExit $VMNAME "BlockJob aborted. Disk full ?"
    fi
    logLineLocal "Copying... $PROGRESS %"
    sleep 5;
  done
}

function getBackupName() {
  # compose the backup name
  local VMNAME=$1
  local BACKUP_IDX=$2
  echo "$BKPATH/$VMNAME/backup-$BACKUP_IDX" 
}

function getLastBackupName() {
  local VMNAME=$1
  local VMBACKUP_IDX=$((MAXBACKUP-1))
  getBackupName "$VMNAME" $VMBACKUP_IDX
}

function fixPath() {
  # get real backup path for a vm
  local VMNAME=$1
  local BASEPATH="$BKPATH/$VMNAME"
  local OLDER_BACKUP_PATH=$(getBackupName $VMNAME $MAXBACKUP)
  # rotate backup
  let BKCNT=$((MAXBACKUP-2))
  while [ $BKCNT -ge 0 ]; do
      let PREVBKCNT=$((BKCNT+1))
      local BKPREV=$(getBackupName $VMNAME $PREVBKCNT)
      local BK=$(getBackupName $VMNAME $BKCNT)
      logLine "Check for move $BK => $BKPREV"
      if [ -d "$BKPREV" ] && [ -d "$BK" ]; then
        logLine "Remove old backup $BKPREV"
        # safety measure
        mv $BKPREV "$BKPATH/$VMNAME/to-be-removed"
        if [ -f "$BKPATH/$VMNAME/to-be-removed/$VMNAME.xml" ]; then
          logLine "Safely remove old backup directory"
          rm -rf "$BKPATH/$VMNAME/to-be-removed"
        else
          logLine "Cannot remove old backup directory. Not a backup."
          doExit 1
        fi
      fi
      if [ -d "$BK" ]; then
        logLine "Rename $BK to $BKPREV"
        mv $BK $BKPREV
      fi
      let BKCNT-=1
  done
  # fix the global-path
  BKPATH=$(getBackupName $VMNAME 0)
  # create the backup directory
  mkdir -p "$BKPATH"
  if [ $? -gt 0 ]; then
    logLine "Problem creating backup path. Exiting."
    doExit 1
  fi
  # fix permissions
  chown -R libvirt-qemu:kvm "$BASEPATH"
}

function checkDiskSpace() {
  local VMNAME=$1
  logLine "Checking required disk space"
  let VMREQSPACE=0
  # get free space on volume
  local DSPACE=$(df "$BKPATH" | grep -v "Available" | awk '{ print $4 }')
  if [ "x$DSPACE" == "x" ]; then
    logFile "Unable to detect disk space for vm"
    doExit 1
  fi
  # for each blockdev get space
  for i in $BLOCKDEVS; do
    local BLKSPACE=$(virsh domblkinfo $VMNAME $i | grep "Physical:" | awk '{ print $2 }')
    local KILOBLKSPACE=$((BLKSPACE / 1024))
    logLine "Device $i requires $KILOBLKSPACE Kbytes"
    let VMREQSPACE+=$KILOBLKSPACE
  done 
  # get memory size (for calculating disk memory needed)
  MEMSIZE=$(virsh dominfo $VMNAME | grep "Max memory" | awk '{ print $3 }')
  if [ "x$MEMSIZE" == "x" ]; then
    logLine "Cannot find VM required memory size"
    doExit 1
  fi
  logLine "VM memory size is $MEMSIZE Kbytes" 
  local VMROUNDMEMSIZE=$(awk "BEGIN{ print int($MEMSIZE*1.2) }")
  logLine "VM memory requirement scaled to $VMROUNDMEMSIZE Kbytes"
  # Add extra 4Gb for memory and xml
  let VMREQSPACE+=$VMROUNDMEMSIZE  
  logLine "Total space required by backup is $VMREQSPACE Kilobytes"
  # get space used by last backup (which will be thrown away)
  local LASTBACKUPNAME=$(getLastBackupName $VMNAME)
  local LASTBACKUPSPACE=$(du -s $LASTBACKUPNAME 2> /dev/null | awk '{ print $1 }')
  if [ "x$LASTBACKUPSPACE" == "x" ]; then
    LASTBACKUPSPACE=0
  fi
  logLine "Last backup $LASTBACKUPNAME occupies $LASTBACKUPSPACE Kbytes"
  # subtract the last backup space from VMREQSPACE
  let VMREQSPACE-=$((LASTBACKUPSPACE))
  # now get available space on device
  local MBSPACEFREE=$((DSPACE / 1024))
  local MBSPACEREQUIRED=$((VMREQSPACE / 1024))
  if [ $DSPACE -lt $VMREQSPACE ]; then
    logLine "Cannot make backup; only ${MBSPACEFREE}Mb avaliable. Minimum needed space is ${MBSPACEREQUIRED}Mb."
    doExit 1
  else
    logLine "Backup possibile: ${MBSPACEFREE}Mb availables vs ${MBSPACEREQUIRED}Mb required."
  fi
}

function backupVM() {
  local VMNAME=$1

  # create the base backup directory if it does not exist and set correct ownership
  mkdir -p "$BKPATH"
  if [ $? -gt 0 ]; then
    logLine "Problem creating base backup directory. Exiting."
    doExit 1
  fi

  # set permissions
  chown -R libvirt-qemu:kvm "$BKPATH"

  # start backup
  logLine "Backup of $VMNAME started"

  # get vm block devices
  getVMBlockDevs $VMNAME

  # check disk space
  checkDiskSpace $VMNAME

  # fix/rotate path
  fixPath $VMNAME
  # dump the vm definition
  dumpVMdefinition $VMNAME
  # make it transient
  undefineVM $VMNAME
  # copy all block devices
  for i in $BLOCKDEVS; do
    copyBlock $VMNAME $i
  done

  # suspend vm (needed to suspend I/O and abort jobs)
  suspendVM $VMNAME
  # abort jobs
  abortAllJobs $VMNAME
  # save vm state and power it off
  saveVMState $VMNAME
  # restore VM state. this is necessary because the save-vm stop the vm 
  restoreVMState $VMNAME
  # restore vm definition
  defineVM $VMNAME

  # end backup
  logLine "Backup of $VMNAME finished"
}

function show_help() {
  echo "bkvm [options] domainname"
  echo -e "\nwith [options] assuming following values:"
  echo "-h or -?          show this help"
  echo "-t DIR            set target directory for backup"
  echo "-m [1-4]          set number of backup to keep" 
  echo "-e EMAIL          send log via mail to address"
}


#
# MAIN CODE
#

while getopts "h?t:m:e:" opt; do
  case "$opt" in
    h|\?)
      show_help
      exit 0
      ;;
    t)
      logLine "Target set to $OPTARG"
      BKPATH=$OPTARG
      ;;
    m)
      if [ "x$OPTARG" == "x" ] || [ $OPTARG -le 0 ] || [ $OPTARG -gt 4 ]; then
        logLine "Invalid number of backups to keep specified. It must be between 1 and 4."
        exit 1
      fi
      logLine "Number of backups to keep set to $OPTARG"
      MAXBACKUP=$OPTARG
      ;;
    e)
      logLine "Sending email to $OPTARG"
      TARGET_EMAIL=$OPTARG
      ;;
  esac
done
shift $((OPTIND-1))

# Parse remaining options

if [ "$1" == "" ]; then
  logLine "Missing VM name"
  exit 1;
fi

# go
VM=$1

# check if vm exists
checkDomain $VM

# finally do the backup
backupVM $VM

# exit and eventually send logs
doExit 0