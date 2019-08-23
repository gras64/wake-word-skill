from os.path import dirname, abspath, os, sys
import time
import uuid
import subprocess
import psutil as psutil
import pyaudio
import wget
from git import Repo
from speech_recognition import Recognizer

from mycroft.client.speech.mic import MutableMicrophone
from mycroft.filesystem import FileSystemAccess
from mycroft.messagebus.message import Message
from mycroft.audio import wait_while_speaking, is_speaking
from mycroft import MycroftSkill, intent_file_handler
from mycroft.util import play_wav, resolve_resource_file
from mycroft.util.time import now_local
from mycroft.util.log import LOG, getLogger

LOGGER = getLogger(__name__)
#try:
#from MycroftSkill.WakeWord.precise.precise.scripts.train import Trainer
#except ImportError:
    #self.log.info("precice not install")

class WakeWord(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        self.record_process = None
        self.start_time = 0
        self.last_index = 24  # index of last pixel in countdowns
        self.source_path = self.file_system.path
        self.piep = resolve_resource_file('snd/start_listening.wav')

        self.settings["min_free_disk"] = 100  # min mb to leave free on disk
        self.settings["rate"] = 16000 # sample rate, hertz
        self.settings["channels"] = 1  # recording channels (1 = mono)
        self.settings["file_path"] = self.file_system.path + "/data"
        self.settings["sell_path"] = self.file_system.path + "/recordings"
        self.settings["duration"] = -1  # default = unknown
        self.settings["formate"] = "S16_LE"
        self.upload = self.settings.get('upload') \
            if self.settings.get('upload') is not None else False
        if not os.path.isdir(self.file_system.path + "/precise/mycroft_precise.egg-info"):
            self.log.info("no precise installed. beginn installation")
            self.install_precice_source()

    def record(self, file_path, duration, rate, channels):
        if duration > 0:
            return subprocess.Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-d",
                str(duration), "-f", str("S16_LE"), file_path])
        else:
            return subprocess.Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-f", str("S16_LE"), file_path])

    def install_precice_source(self):
        if not os.path.isdir(self.file_system.path+"/precise"):
            Repo.clone_from('https://github.com/MycroftAI/mycroft-precise', self.file_system.path+"/precise")
            self.log.info("Downloading precice source")
        if not os.path.isfile(self.file_system.path+"/nonesounds.7z"):
            wget.download('http://downloads.tuxfamily.org/pdsounds/sounds/', self.file_system.path+"/nonesounds")
        self.log.info("installing....")
        self.log.info("Starting installation")
        os.chmod(self.file_system.path + '/precise/setup.sh', 0o755)
        subprocess.call(self.file_system.path+'/precise/setup.sh',
                        preexec_fn=os.setsid, shell=True)


    def has_free_disk_space(self):
        space = (30 * self.settings["channels"] *
                 self.settings["rate"] / 1024 / 1024)
        free_mb = psutil.disk_usage('/')[2] / 1024 / 1024
        return free_mb - space > self.settings["min_free_disk"]

    @intent_file_handler('word.wake.intent')
    def word_wake_intent(self, message):
        if message.data.get("name"):
            name = message.data.get("name")
            self.speak_dialog("word.wake",
                                data={"name": name})
            wait_while_speaking()
                # Throw away any previous recording
            try:
                os.remove(self.settings["file_path"])
            except:
                pass
            time.sleep(4)
            i = 1
            while i <= 4:
                wait_while_speaking()
                time.sleep(1)
                if not self.record_process or wait_while_speaking():
                    play_wav(self.piep)
                    path = "wake-word/"+ self.lang + "-short/"
                    if i == 2:
                        path = "test/wake-word/"+ self.lang + "-short/"
                    soundfile = name+ "-" + self.lang +"."+str(uuid.uuid1())+".wav"
                    self.start_recording(name,i,path,soundfile)
                    i = i + 1
                    #if i == 5:
                        #if not self.ask_yesno("is.all.ok") == "yes":
                         #   i = 1
            wait_while_speaking()
            self.speak_dialog("none.wake.word")
            time.sleep(4)
            i = 1
            while i <= 4:
                wait_while_speaking()
                time.sleep(1)
                if not self.record_process or wait_while_speaking():
                    play_wav(self.piep)
                    path = "not-wake-words/"+ self.lang + "-short/"
                    if i == 2:
                        path = "test/not-wake-words/"+ self.lang + "-short/"
                    soundfile = "not"+ name + "-"+ self.lang +"."+str(uuid.uuid1())+".wav"
                    self.start_recording(name,i,path,soundfile)
                    i = i + 1
                    #if i == 5:
                        #if not self.ask_yesno("is.all.ok") == "yes":
                         #   i = 1
            self.speak_dialog("start.calculating")
            self.calculating(name)






    def start_recording(self, name, i, path, soundfile):
        self.settings["duration"] = 3  # default recording duration


        if self.has_free_disk_space():
            record_for = 3
                # Initiate recording
            wait_while_speaking()
            self.start_time = now_local()   # recalc after speaking completes
            if not os.path.isdir(self.settings["file_path"]+"/"+name +"/"+ path):
                    os.makedirs(self.settings["file_path"]+"/"+name +"/"+ path)
            self.record_process = self.record(self.settings["file_path"]+"/"+name +"/"+ path + soundfile,
                                         int(self.settings["duration"]),
                                         self.settings["rate"],
                                         self.settings["channels"])
            self.enclosure.eyes_color(255, 0, 0)  # set color red
            self.last_index = 24
            self.schedule_repeating_event(self.recording_feedback, None, 1,
                                          name='RecordingFeedback')
        else:
            self.speak_dialog("disk.full")

    def recording_feedback(self, message):
        if not self.record_process:
            self.end_recording()
            return

        # Verify there is still adequate disk space to continue recording
        if self.record_process.poll() is None:
            if not self.has_free_disk_space():
                # Out of space
                self.end_recording()
                self.speak_dialog("audio.record.disk.full")
        else:
            # Recording ended for some reason
            self.end_recording()

    def end_recording(self):
        self.cancel_scheduled_event('RecordingFeedback')

        if self.record_process:
            # Stop recording
            self.stop_process(self.record_process)
            self.record_process = None
            # Calc actual recording duration
            self.settings["duration"] = (now_local() -
                                         self.start_time).total_seconds()

        # Reset eyes
        self.enclosure.eyes_color(34, 167, 240)  # Mycroft blue
        self.bus.emit(Message('mycroft.eyes.default'))

        # Standard Stop handler
    def stop(self):
        if self.record_process:
            self.end_recording()
            return True

    @staticmethod
    def stop_process(process):
        if process.poll() is None:  # None means still running
            process.terminate()
            # No good reason to wait, plus it interferes with
            # how stop button on the Mark 1 operates.
            # process.wait()
            return True
        else:
            return False

    def calculating(self, name):
        self.log.info("calculating")
       # if not os.path.isdir(self.settings["file_path"]+"/"+name+"/not-wake-words/noises"):
            # Create a ZipFile Object and load sample.zip in it
            #with libfile.extract_file(self.file_system.path+"/nonesounds.7z", 'r') as zipObj:
             #   zipObj.extractall(self.settings["file_path"]+"/"+name+"/not-wake-words/noises")
            #ZipFile.extractall(self.file_system.path+"/nonesounds.7z", self.settings["file_path"]+"/"+name+"/not-wake-words/noises")
        if self.settings.get("precise_calc_pid") is None:
            self.log.info("weiter")
            #if os.isdir(self.settings["file_path"]+name+"/not-wake-words"):
            precise_calc = subprocess.Popen([self.file_system.path+"/precise/.venv/bin/python "+
                                        self.file_system.path+"/precise/precise/scripts/train.py "+
                                        self.file_system.path+"/"+name+".net "+
                                        self.settings["file_path"]+"/"+name+" -e "+ str(600)],
                                        bufsize=-1, preexec_fn=os.setsid, shell=True)
            self.settings["precise_calc_pid"] = precise_calc.pid
            self.schedule_repeating_event(self.precise_check, None, 1,
                                          name='PreciseCalc')
            return True
        else:
            return False
        return True

    def precise_check(self, name):
        if not self.precise_calc:
            self.cancel_scheduled_event('PreciseCalc')
            self.speak_dialog("end.calculating",
                            data={"name": name})


   # def config(self, name):
    #    from mycroft.configuration.config import (
   #         LocalConf, USER_CONFIG, Configuration
  #      )
  #      module = message.data['ListenerType'].replace(' ', '')
  #      module = module.replace('default', 'pocketsphinx')
  #      name = module.replace('pocketsphinx', 'pocket sphinx')

  #      if self.get_listener() == module:
 #           self.speak_dialog('listener.same', data={'listener': name})
  #          return

  #      wake_word = Configuration.get()['listener']['wake_word']

 #       new_config = {
#            'hotwords': {wake_word: {'module': module}}
 #       }
 #       user_config = LocalConf(USER_CONFIG)
 #       user_config.merge(new_config)
 #       user_config.store()

 #       self.bus.emit(Message('configuration.updated'))

#        if module == 'precise':
 #           engine_folder = expanduser('~/.mycroft/precise/precise-engine')
  #          if not isdir(engine_folder):
  #              self.speak_dialog('download.started')
  #              return

   #     self.speak_dialog('set.listener', data={'listener': name})

 #   def get_listener(self):
 #       """Raises ImportError or KeyError if not supported"""
#        from mycroft.configuration.config import Configuration
 #       wake_word = Configuration.get()['listener']['wake_word']
 #       ww_config = Configuration.get()['hotwords'].get(wake_word, {})
 #       return ww_config.get('module', 'pocketsphinx')


    @intent_file_handler('upload.intent')
    def upload_intent(self, message):
        self.upload = True


    def shutdown(self):
        super(WakeWord, self).shutdown()


def create_skill():
    return WakeWord()

