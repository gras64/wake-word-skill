from os.path import dirname, expanduser, abspath, os, sys
import time
import uuid
import subprocess
import psutil as psutil
import pyaudio
import wget
import _thread
import py7zr
import tarfile
import linecache
import shutil
from git import Repo
from speech_recognition import Recognizer

from mycroft.filesystem import FileSystemAccess
from mycroft.messagebus.message import Message
from mycroft.audio import wait_while_speaking, is_speaking
from mycroft import MycroftSkill, intent_file_handler
from mycroft.util import play_wav, resolve_resource_file
from mycroft.util.time import now_local
from mycroft.util.log import LOG, getLogger

LOGGER = getLogger(__name__)

class WakeWord(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    def initialize(self):
        self.record_process = None
        self.start_time = 0
        self.last_index = 24  # index of last pixel in countdowns
        self.source_path = self.file_system.path
        self.piep = resolve_resource_file('snd/start_listening.wav')

        self.settings["name"] = self.config_core.get('listener', {}).get('wake_word').replace(' ', '-')
        self.settings["soundbackup"] = self.settings.get('soundbackup', False)
        self.settings["min_free_disk"] = 100  # min mb to leave free on disk
        self.settings["rate"] = 16000 # sample rate, hertz
        self.settings["channels"] = 1  # recording channels (1 = mono)
        self.settings["file_path"] = self.file_system.path + "/data"
        self.settings["sell_path"] = "/tmp/mycroft_wake_words"
        self.settings["duration"] = -1  # default = unknown
        self.settings["formate"] = "S16_LE"
        self.settings["selling"] = self.settings.get('selling', 15)
        self.settings["improve"] = 10
        self.settings['savewakewords'] = self.settings.get('savewakewords', False)
        if not os.path.isdir(self.file_system.path + "/precise/mycroft_precise.egg-info"):
            self.log.info("no precise installed. beginn installation")
            _thread.start_new_thread(self.install_precise_source, ())
        if self.settings["soundbackup"] is True:
            _thread.start_new_thread(self.download_sounds, ())
        self.save_wakewords()

         ## Wait vor wakeword
        #_wait_until_wake_word(source, sec_per_buffer):


    def record(self, file_path, duration, rate, channels):
        if duration > 0:
            return subprocess.Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-d",
                str(duration), "-f", str(self.settings["formate"]), file_path])
        else:
            return subprocess.Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-f", str(self.settings["formate"]), file_path])

    @intent_file_handler('install.precise.source.intent')
    def install_precise_source(self):
        if not os.path.isdir(self.file_system.path+"/precise"):
            self.speak_dialog("download.started")
            self.log.info("Downloading precice source")
            Repo.clone_from('https://github.com/MycroftAI/mycroft-precise', self.file_system.path+"/precise")
        #else:
         #   Repo.pull('https://github.com/MycroftAI/mycroft-precise', self.file_system.path+"/precise")
        self.log.info("Starting installation")
        platform = self.config_core.get('enclosure', {}).get('platform')
        os.chmod(self.file_system.path + '/precise/setup.sh', 0o755)
        subprocess.call(self.file_system.path+'/precise/setup.sh',
                        preexec_fn=os.setsid, shell=True)
        #### TO DO
        ### dirty solution for fail on my raspberry
        if platform == "picroft":
            subprocess.call([self.file_system.path+"/precise/.venv/bin/python -m pip install tensorflow==1.10.1"],
                                preexec_fn=os.setsid, shell=True)

        self.log.info("end installation")
        self.speak_dialog("installed.OK")


    def has_free_disk_space(self):
        space = (30 * self.settings["channels"] *
                 self.settings["rate"] / 1024 / 1024)
        free_mb = psutil.disk_usage('/')[2] / 1024 / 1024
        return free_mb - space > self.settings["min_free_disk"]

    @intent_file_handler('wake.word.intent')
    def wake_word_intent(self, message):
        name = message.data.get("name")
        name = name.replace(' ', '-')
        if name == self.config_core.get('listener', {}).get('wake_word').replace(' ', '-'):
            self.train_wake_word_intent(message)
            return
        else:
            self.config(name, message)

    def event(self):
        self.log.info("test schleife")

    @intent_file_handler('train.wake.word.intent')
    def train_wake_word_intent(self, message):
        if message.data.get("name"):
            name = message.data.get("name")
            name = name.replace(' ', '-')
            if os.path.isdir(self.settings["file_path"]+"/"+name):
                if self.ask_yesno("model.available",
                                data={"name": name}) == "yes":
                    rmtree(self.settings["file_path"]+"/"+name)
            self.speak_dialog("word.wake",
                                data={"name": name})
            wait_while_speaking()
                # Throw away any previous recording
            time.sleep(4)
            i = 1
            while i <= 12:
                wait_while_speaking()
                time.sleep(1)
                if not self.record_process or wait_while_speaking():
                    play_wav(self.piep)
                    path = "wake-word/"+ self.lang[:2] + "-short/"
                    if i >= 9:
                        path = "test/wake-word/"+ self.lang[:2]+ "-short/"
                    soundfile = name+ "-" + self.lang[:2] +"-"+str(uuid.uuid1())+".wav"
                    self.start_recording(name,i,path,soundfile)
                    i = i + 1
            wait_while_speaking()
            self.speak_dialog("none.wake.word")
            time.sleep(4)
            i = 1
            while i <= 12:
                wait_while_speaking()
                time.sleep(1)
                if not self.record_process or wait_while_speaking():
                    play_wav(self.piep)
                    path = "not-wake-word/"+ self.lang[:2] + "-short/"
                    if i >= 9:
                        path = "test/not-wake-word/"+ self.lang[:2] + "-short/"
                    soundfile = "not"+name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav"
                    self.start_recording(name,i,path,soundfile)
                    i = i + 1
            self.speak_dialog("start.calculating")
            self.calculating_intent(name, message)

    def start_recording(self, name, i, path, soundfile):
        self.settings["duration"] = 3  # default recording duration


        if self.has_free_disk_space():
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

    def calculating_intent(self, name, message):
        self.log.info("calculating")
        self.settings["name"] = name
        if self.download_sounds:
            self.precise_calc = subprocess.Popen([self.file_system.path+"/precise/.venv/bin/python "+
                                    self.file_system.path+"/precise/precise/scripts/train.py "+
                                    self.file_system.path+"/"+name+".net "+
                                    self.settings["file_path"]+"/"+name+" -e "+ str(600)],
                                    preexec_fn=os.setsid, shell=True)
            self.schedule_repeating_event(self.precise_calc_check, None, 3,
                                          name='PreciseCalc')
            return True

    def download_sounds(self):
        if self.settings["soundbackup"] is True:
            import py7zr
            name = self.settings["name"]
            if not os.path.isfile(self.file_system.path+"/nonesounds.7z"):
                free_mb = psutil.disk_usage('/')[2] / 1024 / 1024
                if free_mb <= 1500:
                    self.settings["soundbackup"] = False
                    self.log.info("no space: Sound Download not possible")
                    return
                else:
                    self.log.info("downloading soundbackup")
                    wget.download('http://downloads.tuxfamily.org/pdsounds/pdsounds_march2009.7z', self.file_system.path+"/nonesounds.7z")
            if not os.path.isdir(self.settings["file_path"]+"/"+name+"/not-wake-word/noises"):
                if not os.path.isdir(self.file_system.path+"/noises"):
                    os.makedirs(self.file_system.path+"/noises")
                if not os.path.isdir(self.file_system.path+"/noises/mp3"):
                    self.log.info("unzip soundbackup")
                    py7zr.unpack_7zarchive(self.file_system.path+"/nonesounds.7z", self.file_system.path+"/noises")
                    self.log.info("download sucess, start convert")
                if not os.path.isdir(self.file_system.path+"/noises/noises"):
                    folder = self.file_system.path+"/noises/mp3/"
                    fileformat = '.mp3'
                    i = 1
                    while i <= 2:
                        for root, dirs, files in os.walk(folder):
                            for f in files:
                                filename = os.path.join(root, f)
                                if filename.endswith(fileformat):
                                    self.log.info("Filename: "+filename)
                                    soundfile = filename.replace(fileformat, '').replace(folder, '')
                                    if not os.path.isdir(self.file_system.path+"/noises/noises"):
                                        os.makedirs(self.file_system.path+"/noises/noises")
                                    subprocess.call(["ffmpeg -i "+filename+" -acodec pcm_s16le -ar 16000 -ac 1 -f wav "+
                                                    self.file_system.path+"/noises/noises/"+soundfile+".wav"],
                                                    preexec_fn=os.setsid, shell=True)
                                    self.log.info("extratct: "+filename)
                        folder = self.file_system.path+"/noises/otherformats/"
                        fileformat = '.flac'
                        i = i + 1
                    self.speak_dialog("download.success")
                if not os.path.isdir(self.settings["file_path"]+"/"+name+"/not-wake-word"):
                    os.makedirs(self.settings["file_path"]+"/"+name+"/not-wake-word")
                if not os.path.isdir(self.settings["file_path"]+"/"+name+"/not-wake-word/noises"):
                    self.log.info("Make Filelink")
                    os.symlink(self.file_system.path+"/noises/noises/", self.settings["file_path"]+"/"+name+"/not-wake-word/noises")
        else:
            return True


    def precise_calc_check(self, message):
        self.log.info("precise: check for end calculation ")
        name = self.settings["name"]
        if self.precise_calc.poll():
            self.cancel_scheduled_event('PreciseCalc')
            if os.path.isfile(self.file_system.path+"/"+self.settings["name"]+".net"):
                self.precise_con(name, message)

    def precise_con_check(self, message):
        self.log.info("precise: check for end converting ")
        name = self.settings["name"]
        if self.precise_convert.poll():
            self.cancel_scheduled_event('PreciseConvert')
            if not self.select_precise_file is None:
                self.speak_dialog("end.calculating",
                        data={"name": self.settings["name"]})
                self.config(name, message)

    def precise_con(self, name, message):
        self.log.info("precise: start convert to .pb")
        self.precise_convert = subprocess.Popen([self.file_system.path+"/precise/.venv/bin/python "+
                                    self.file_system.path+"/precise/precise/scripts/convert.py -o "+
                                    self.file_system.path+"/"+name+".pb "+
                                    self.file_system.path+"/"+name+".net "],
                                    bufsize=-1, preexec_fn=os.setsid, shell=True)
        self.schedule_repeating_event(self.precise_con_check, None, 3,
                                      name='PreciseConvert')
        return True

    def select_precise_file(self, name, message):
        if os.path.isfile(self.file_system.path+"/"+name+".pb"):
            precise_file = self.file_system.path+"/"+name+".pb"
            return precise_file
        elif os.path.isfile(self.file_system.path+"/"+name+".net"):
            self.precise_con(name, message)
            return None
        elif resolve_resource_file("precise/"+name+".pb"):
            precise_file = resolve_resource_file("precise/"+name+".pb")
            return precise_file
        else:
            self.train_wake_word_intent(message)
            return None



    def config(self, name, message):
        from mycroft.configuration.config import (
            LocalConf, USER_CONFIG, Configuration
        )
        module = "precise".replace(' ', '')
        module = module.replace('default', 'pocketsphinx')

        precise_file = self.select_precise_file(name, message)
        if precise_file == None:
            self.log.info("precise file "+name+" not found")
            return
        else:
            self.log.info("set precise file: "+precise_file)

            wake_word = name
            self.log.info("set precise WakeWord:"+name)
            new_config = {"listener": {"wake_word": name, "record_wake_words": "true"}, "hotwords": {wake_word:
                        {"module": module, "threshold": "1e-90", "lang": self.lang,"local_model_file": precise_file}}
            }
            user_config = LocalConf(USER_CONFIG)
            user_config.merge(new_config)
            user_config.store()

            self.bus.emit(Message('configuration.updated'))

            if module == 'precise':
                engine_folder = expanduser('~/.mycroft/precise/precise-engine')
                if not os.path.isdir(engine_folder):
                    self.speak_dialog('download.started')
                    return

            self.speak_dialog('end.calculating', data={'name': name})


    @intent_file_handler('improve.intent')
    def improve_intent(self, message):
        name = self.config_core.get('listener', {}).get('wake_word').replace(' ', '-')
        i = 1
        if os.path.isdir(self.settings["sell_path"]):
            onlyfiles = next(os.walk(self.settings["sell_path"]))[2]
            if len(onlyfiles) <= self.settings["improve"]:
                selling = len(onlyfiles)
            else:
                selling = self.settings["improve"]
            self.speak_dialog('improve', data={'name': name, "selling": selling})
            self.log.info("search wake word in: "+self.settings["sell_path"])
            for root, dirs, files in os.walk(self.settings["sell_path"]):
                for f in files:
                    filename = os.path.join(root, f)
                    if filename.endswith('.wav'):
                        if i <= selling:
                            self.log.info("play file")
                            play_wav(filename)
                            sell = self.ask_yesno("ask.sell", data={'i': i})
                            i = i+1
                            path = None
                            if sell == "yes":
                                path = self.settings["file_path"]+"/"+name+"/wake-word/"+self.lang[:2]+"-short/"
                            elif sell == "no":
                                path = self.settings["file_path"]+"/"+name+"/not-wake-word/"+self.lang[:2]+"-short-not/"
                            if not path is None:
                                if not os.path.isdir(path):
                                    os.makedirs(path)
                                file = path+name+"-"+self.lang[:2]+"-"+str(uuid.uuid1())+".wav"
                                if not os.path.isfile(file):
                                    os.rename(filename, file)
                                    self.log.info("move File: "+file)
                            else:
                                os.remove(filename)
                else:
                    self.speak_dialog('improve.no.file', data={'name': name})
            self.calculating_intent(name, message)
        else:
            self.speak_dialog('improve.no.file', data={'name': name})



    @intent_file_handler('upload.intent')
    def upload_intent(self, message):
        if message.data.get("name"):
            name = message.data.get("name")
            name = name.replace(' ', '-')
        else:
            name = self.config_core.get('listener', {}).get('wake_word')
        if os.path.isfile(self.file_system.path+"/"+name+".pb"):
            self.git_download(name)
            self.prepaire_repo(name)
            self.git_upload(name)
        elif os.path.isfile(self.file_system.path+"/"+name+".net"):
            self.precise_con(name, message)
            self.git_download(name)
            self.prepaire_repo(name)
            self.git_upload(name)
        else:
            self.log.info("no precise file for: "+name)
            self.speak_dialog("no.file")

    def git_download(self, name):
        repo = Repo(self.file_system.path+"/Precise-Community-Data")
        repo.config_writer().set_value("user", "name", self.settings.get('localgit')).release()
        repo.config_writer().set_value("user", "email", self.settings.get('gitmail')).release()
        if not os.path.isdir(self.file_system.path+"/Precise-Community-Data"):
            self.log.info("Downloading Precise Comunity Data")
            Repo.clone_from('https://github.com/MycroftAI/Precise-Community-Data.git', self.file_system.path+"/Precise-Community-Data")
        else:
            self.log.info("pull Precise Comunity Data")
            origin = repo.remote('origin')
            origin.pull()

    def prepaire_repo(self, name):
        name = name.replace('-', '').replace(' ', '')
        ##### Model Files
        self.log.info("make repo ready vor upload")
        precisefolder = self.file_system.path+"/Precise-Community-Data"
        presiceversion = linecache.getline(self.file_system.path + "/precise/mycroft_precise.egg-info/PKG-INFO", 3).replace('Version: ', '')[:5]
        if not os.path.isdir(precisefolder+"/"+name+"/models/"):
            os.makedirs(precisefolder+"/"+name+"/models/")
        tar = tarfile.open(precisefolder+"/"+name+"/models/"+name+"-"+self.lang[:3]+presiceversion+"-"+
                            time.strftime("%Y%m%d")+"-"+self.settings.get('localgit')+".tar.gz", "w:gz")
        for name in [self.file_system.path+"/"+name+".pb", self.file_system.path+"/"+name+".pbtxt",
                    self.file_system.path+"/"+name+".pb.params"]:
            tar.add(name)
        ###### licenses
        licensefile = precisefolder+"/licenses/licenses-"+time.strftime("%Y%m%d")+"-"+self.settings.get('localgit')+".txt"
        shutil.copy(precisefolder+"/licenses/license-template.txt", licensefile)
        open(licensefile, "r").replace('I, [author name]', 'I, '+self.settings.get('localgit')+
            ' (https://github.com/'+self.settings.get('localgit')+')')


        #shutil.copytree(self.settings["file_path"]+"/"+name+"/wake-word/"+self.lang[:2]+"-short/", precisefolder)


    def git_upload(self,name):
        self.speak_dialog("upload.success", data={'name': name})

    def save_wakewords(self):
        from mycroft.configuration.config import (
            LocalConf, USER_CONFIG, Configuration
        )
        record = Configuration.get()['listener']['record_wake_words']
        if self.settings["savewakewords"] is True:
            free_mb = psutil.disk_usage('/')[2] / 1024 / 1024
            if free_mb <= self.settings["min_free_disk"]:
                self.log.info("no space: deactivate recording")
                new_config = {"listener": {"record_wake_words": "true"}}
                user_config = LocalConf(USER_CONFIG)
                user_config.merge(new_config)
                user_config.store()
            if record == "false":
                new_config = {"listener": {"record_wake_words": "true"}}
                self.log.info("set wake word recording")
                user_config = LocalConf(USER_CONFIG)
                user_config.merge(new_config)
                user_config.store()
                self.bus.emit(Message('configuration.updated'))
        else:
            if record == "true":
                new_config = {"listener": {"record_wake_words": "false"}}
                self.log.info("unset wake word recording")
                user_config = LocalConf(USER_CONFIG)
                user_config.merge(new_config)
                user_config.store()
                self.bus.emit(Message('configuration.updated'))


    def shutdown(self):
        super(WakeWord, self).shutdown()
        self.settings.update


def create_skill():
    return WakeWord()
