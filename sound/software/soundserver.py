#!/usr/bin/python -u

import sys, os, subprocess, signal, re, threading

from Queue import Queue
import time

#----------------------------------------------------------------------
scriptDir = os.path.abspath(os.path.dirname(__file__))

#----------------------------------------------------------------------

serialBaud = 115200

useSerial = True 



soundsDir = os.path.join(scriptDir, "../sounds")

# if not None, lines not starting with this string
# are ignored from the serial input
# serialPrefix = '!'
serialPrefix = None

#----------------------------------------------------------------------

def findSerial():
    import glob

    fnames = glob.glob("/dev/tty.usbmodem*")

    if not fnames:
        # none found
        return None

    # return the first one
    return fnames[0]


#----------------------------------------------------------------------

class SoundPlayer:
    # class to play a sound once or in a loop
    # this inherits from thread 

    #----------------------------------------

    def __init__(self, soundFile, channel, loop = False):

        self.loop = loop
        self.channel = channel

        # keep original sound file name
        self.soundFile = soundFile
        self.stopFlag = False

        self.proc = None

    #----------------------------------------
    def run(self):

        while True:
            if self.stopFlag:
                break

            self.proc = subprocess.Popen(
                ["/usr/bin/afplay", self.soundFile])
            
            # wait for the process to complete
            self.proc.wait()

            self.proc = None

            if not self.loop:
                break

    #----------------------------------------

    def kill(self):
        # kill the external process
        self.stopFlag = True

        if self.proc != None:
            try:
                os.kill(self.proc.pid, signal.SIGTERM)
            except Exception, ex:
                print "got exception killing the sound thread with pid",self.proc.pid,":",ex


    #----------------------------------------


#----------------------------------------------------------------------

class QueueProcessor(threading.Thread):
    # class to process requests
    # for playing sounds in a queue

    #----------------------------------------

    def __init__(self):
        threading.Thread.__init__(self)
        
        self.threads = Queue()
        self.stopFlag = False
        self.currentThread = None

    #----------------------------------------

    def add(self, thread):

        self.threads.put(thread)

    #----------------------------------------

    def run(self):
        # process threads 
        while not self.stopFlag:
            self.currentThread = self.threads.get()

            if self.stopFlag:
                return

            self.currentThread.run()

    #----------------------------------------

    def clear(self):
        # clear all pending threads
        while not self.threads.empty():
            self.threads.get()

    #----------------------------------------

    def kill(self):
        # kill the currently running process
        if self.currentThread != None:
            self.currentThread.kill()

        # self.currentThread.join()



#----------------------------------------------------------------------

class GenericReader(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.cmdHandler = None
        self.stopFlag = False

    def register(self, cmdHandler):
        self.cmdHandler = cmdHandler

    def stop(self):
        self.stopFlag = True

    def run(self):
        while not self.stopFlag:
            cmd = self.input.readline()

            if cmd != '':
                if self.cmdHandler != None:
                    self.cmdHandler.addCmd(cmd)

#----------------------------------------------------------------------
class SerialReader(GenericReader):
    # class reading commands from the serial line

    #----------------------------------------

    def __init__(self, serialBaud, prefix):
        GenericReader.__init__(self)

        import serial
        self.input = None
        self.prefix = prefix

    #----------------------------------------

    def openSerial(self):
        # tries to find an usb serial device and opens it
        serialDevice = findSerial()

        import serial

        if serialDevice == None:
            return None
        else:
            print "using",serialDevice
            os.system("say 'serial device connected'")
            return serial.Serial(serialDevice, serialBaud, 
                                   timeout=0.1
                                   )        

    #----------------------------------------

    def run(self):
        import serial

        while not self.stopFlag:

            if self.input == None:
                self.input = self.openSerial()
                if self.input == None:
                    # no input device found
                    time.sleep(1)
                    continue
                # we opened a new serial device
                                 

            try:
                cmd = self.input.readline()
            except serial.serialutil.SerialException, ex:
                    self.input = None
                    print "serial device disappeared"
                    os.system("say 'serial device disconnected, exiting'")

                    os.kill(os.getpid(), signal.SIGKILL)

            if cmd == '':
                continue
            
            # ignore these debug messages
            if cmd.startswith('A0='):
               continue

            if self.cmdHandler == None:
                continue

            # remove prefix if specified
            if self.prefix != None:
                if not cmd.startswith(self.prefix):
                    continue

                # remove prefix
                cmd = cmd[len(self.prefix):]

            self.cmdHandler.addCmd(cmd)

    #----------------------------------------

#----------------------------------------------------------------------

class StdinReader(GenericReader):
    def __init__(self):
        GenericReader.__init__(self)

        self.input = sys.stdin


#----------------------------------------------------------------------

class CmdHandler:
    
    #----------------------------------------

    def __init__(self, inputSources):

        # register ourselves as callback to the input sources
        self.inputSources = list(inputSources)
        for source in self.inputSources:
            source.register(self)
            source.start()

        self.cmdQueue = Queue()

        self.stopFlag = False

        # soun   d queues
        # maps from queue name to list of threads to process
        self.soundQueues = {}


    #----------------------------------------

    fileAliases = {
        "0": "87045__runnerpack__weapgone.wav",
        "1": "345833__krzysiunet__game-over-2.wav",
        "2": "342756__rhodesmas__failure-01.wav",
        "3": "173958__fins__failure.wav",
        "4": "328120__kianda__powerup.wav",
        }

    def __expandAlias(self, cmdParts):
        
        retval = list(cmdParts)

        if (cmdParts[0] == 'play' or cmdParts[0] == 'loop') and len(cmdParts) >= 2:
            # expand file name aliases
            retval[1] = self.fileAliases.get(retval[1],retval[1])


        return retval


    #----------------------------------------


    def __enqueueSound(self, cmdArgs, loop):
        if len(cmdArgs) < 1:
            print "missing sound file"
            return

        origSoundFile = cmdArgs[0]

        # remove any directory from the sound file name
        soundFile = os.path.basename(origSoundFile)

        soundFile = os.path.abspath(
            os.path.join(soundsDir, soundFile))

        if not os.path.exists(soundFile):
            print "sound file", origSoundFile,"not found"
            return

        #----------

        if len(cmdArgs) >= 2:
            channel = cmdArgs[1].lower()
            if len(channel) != 1:
                print "channel name must be exactly one character"
                return
        else:
            channel = 'a'

        # check if this queue exists already
        if not self.soundQueues.has_key(channel):
            self.soundQueues[channel] = QueueProcessor()
            self.soundQueues[channel].start()

        # kill the current sound in this queue
        self.soundQueues[channel].clear()
        self.soundQueues[channel].kill()

        # enqueue sound 
        self.soundQueues[channel].add(SoundPlayer(soundFile, channel, loop))

    #----------------------------------------

    def __processCmd(self, cmdParts):
        cmdParts = self.__expandAlias(cmdParts)

        if not cmdParts:
            return

        #----------

        if cmdParts[0] == 'play' or cmdParts[0] == 'loop':
            self.__enqueueSound(cmdParts[1:], cmdParts[0] == 'loop')
            return

        #----------

        if cmdParts[0] == 'silence':
            
            if len(cmdParts) >= 2:
                channel = cmdParts[1].lower()
                if len(channel) > 1:
                    print "channel name must be exactly one character"
                    return

                channels = [ channel ] 
            else:
                # silence all channels
                channels = self.soundQueues.keys()

            # kill all running threads and clear the pending ones
            for channel in channels:
                queue = self.soundQueues.get(channel, None)
                if queue == None:
                    print "warning: channel",channel,"not found"
                    continue

                queue.clear()
                queue.kill()

            return

        #----------

        if cmdParts[0] == 'stop':
            # stop the currently running thread

            if len(cmdParts) < 2:
                print "missing channel name"
                return

            channel = cmdParts[1].lower()
            if len(channel) > 1:
                print "channel name must be exactly one character"
                return
            
            queue = self.soundQueues.get(channel, None)
            if queue == None:
                print "warning: channel",channel,"not found"
                return

            # kill the currently running sound
            queue.kill()

            return

        #----------

        if cmdParts[0] == 'exit':
            # end input sources
            for source in self.inputSources:
                source.stopFlag = True

            for source in self.inputSources:
                source.join()
                print "joined one source"

            print "joined sources"

            # kill all remaining threads
            for queue in self.soundQueues.values():
                queue.stopFlag = True

                queue.clear()
                queue.kill()
                
                # inject an empty thread to unblock the queue.get(..)
                queue.add(threading.Thread())

                queue.join()


            self.stopFlag = True
            

            return

        print "unknown command '%s'" % cmdParts[0]

    #----------------------------------------

    def addCmd(self, cmd):
        # enqueue a command
        self.cmdQueue.put(cmd)

    #----------------------------------------

    def loop(self):
        # the 'eternal' loop accepting commands

        while not self.stopFlag:
            print ">",; sys.stdout.flush()

            cmd = self.cmdQueue.get()
            if cmd == '':
                continue

            print cmd

            parts = re.split('\s+', cmd.strip())

            # execute commands
            self.__processCmd(parts)

#----------------------------------------------------------------------

class VolumeAdjuster(threading.Thread):
    # thread class which will try to set the volume
    # until the first time it got a non-zero exit status
    
    def __init__(self, volume = 100):
        threading.Thread.__init__(self)

        self.volume = volume
        self.stopFlag = False

    def run(self):
        while not self.stopFlag:
            res = os.system("/usr/bin/osascript -e 'set volume output volume %d'" % self.volume)
            if res == 0:
                print "succesfully set volume to %d" % self.volume
                break
            
            time.sleep(1)

    



#----------------------------------------------------------------------
# main
#----------------------------------------------------------------------

if __name__ == '__main__':

    # start volume adjuster
    volumeAdjuster = VolumeAdjuster()
    volumeAdjuster.start()

    # start a server listening on the tty usb serial port

    # open the serial port
    sources = []
    if useSerial:
        sources.append(SerialReader(serialBaud,
                                    prefix = serialPrefix))
        
    sources.append(StdinReader())

    cmdHandler = CmdHandler(sources)

    os.system("say 'sound server started'")

    cmdHandler.loop()

    volumeAdjuster.stopFlag = True
    volumeAdjuster.join()
