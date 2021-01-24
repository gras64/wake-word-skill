#import base64
import linecache
import shutil
import tarfile
import time
import uuid
from os.path import abspath, dirname, expanduser, os, sys
from shutil import rmtree
## from presice trainer
import wave
import platform
from os.path import join
import posixpath
from os import makedirs
from functools import partial
from time import sleep
from threading import Thread, Event
from petact import install_package
from tempfile import mkstemp, mkdtemp
from subprocess import call, Popen
from glob import glob
from math import sqrt
##

import psutil as psutil

import _thread
import git
import pyaudio
import wget
from github import Github, GithubException  # 
from msk.exceptions import GithubRepoExists
from mycroft import MycroftSkill, intent_file_handler
from mycroft.audio import is_speaking, wait_while_speaking
from mycroft.filesystem import FileSystemAccess
from mycroft.messagebus.message import Message
from mycroft.session import SessionManager
from mycroft import FallbackSkill
from mycroft.util import play_wav, resolve_resource_file
from mycroft.util.log import LOG, getLogger
from mycroft.util.parse import fuzzy_match
from mycroft.util.time import now_local
#from github.Repository import Repository #
from speech_recognition import Recognizer

LOGGER = getLogger(__name__)

class WakeWord(FallbackSkill):
    urls = {
        'x86_64': 'https://github.com/MycroftAI/mycroft-precise/releases'
                  '/download/v0.3.0/precise-all_0.3.0_x86_64.tar.gz',
        'armv7l': 'https://github.com/MycroftAI/mycroft-precise/releases'
                  '/download/v0.3.0/precise-all_0.3.0_armv7l.tar.gz',
    }
    train_model_base_url = 'https://raw.githubusercontent.com/MycroftAI' \
                           '/precise-data/models/{wake_word}.train.tar.gz'
    # TODO: Replace with downloaded data
    noise_folder = ''
    chunk_size = 2048
    threshold = 0.1


    def __init__(self):
        super(WakeWord, self).__init__()
        self.url = self.urls.get(platform.machine(), '')
        self.platform_supported = bool(self.url)
        if self.url and not self.url.endswith('.tar.gz'):
            self.url = requests.get(self.url).text.strip()

        self.folder = expanduser('~/.mycroft/precise-trainer')
        self.precise_config = self.config_core['precise']
        self.model_url = self.train_model_base_url.format(
            wake_word='hey-mycroft'
        )
        self.model_file = join(self.folder, posixpath.basename(
            self.model_url)).replace(
            '.tar.gz', '.net'
        )

        self.exe_folder = join(self.folder, 'precise')
        self.engine_exe = join(self.exe_folder, 'precise-engine')
        self.convert_exe = join(self.exe_folder, 'precise-convert')

        makedirs(self.folder, exist_ok=True)
        self.install_thread = Thread(target=self.install_package)
        self.install_thread.start()
        self.install_complete = Event()
        self.install_failed = False

    def initialize(self):
        self.record_process = None
        self.start_time = 0
        self.last_index = 24  # index of last pixel in countdowns
        self.source_path = self.file_system.path
        self.piep = resolve_resource_file('snd/start_listening.wav')
        self.precisefolder = self.file_system.path+"/Precise-Community-Data"
        self.settings["Name"] = self.config_core.get('listener', {}).get('wake_word').replace(' ', '-')
        self.settings["min_free_disk"] = 100  # min mb to leave free on disk
        self.settings["rate"] = 16000 # sample rate, hertz
        self.settings["channels"] = 1  # recording channels (1 = mono)
        self.settings["file_path"] = self.file_system.path + "/data/"
        self.settings["sell_path"] = "/tmp/mycroft_wake_words"
        self.settings["duration"] = -1  # default = unknown
        self.settings["formate"] = "S16_LE"
        self.settings["selling"] = self.settings.get('selling', 15)
        self.settings["improve"] = 10
        self.settings["onlyPrecise"] = self.settings.get('onlyPrecise', True)
        self.settings["usevalidator"] = self.settings.get('usevalidator', True)
        self.settings['savewakewords'] = self.settings.get('savewakewords', False)
        self.settings['oploadserver'] = self.settings.get('oploadserver', False)
        self.settings["wwnr"] = self.settings.get('wwnr', 12)
        self.settings["nowwnr"] = self.settings.get('nowwnr', 12)
        self.settings["repo"] = self.settings.get('repo', 'https://github.com/MycroftAI/Precise-Community-Data.git')
        self.save_wakewords()
        if self.settings['oploadserver']:
            self.recording_server = Popen('python -m http.server 8082', cwd=self.file_system.path+"/data",
                                    preexec_fn=os.setsid, shell=True)
            self.log.info("load server success")
        #self.bus.emit(Message('notification:alert',
        #                        {'skill': "test2"}))

         ## Wait vor wakeword
        #_wait_until_wake_word(source, sec_per_buffer):
        self.recordfile = ""


    def record(self, file_path, duration, rate, channels):
        if duration > 0:
            return Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-d",
                str(duration), "-f", str(self.settings["formate"]), file_path])
        else:
            return Popen(
                ["arecord", "-r", str(rate), "-c", str(channels), "-f", str(self.settings["formate"]), file_path])

    def on_download(self, name):
        self.log.info('Download for {} started!'.format(name))
        while not self.install_complete.is_set():
            self.log.info('Still downloading {}...'.format(name))
            sleep(5)
        self.log.info('Download of {} {}!'.format(
            name, 'failed' if self.install_failed else 'completed'
        ))

    @intent_file_handler('install.precise.source.intent')
    def install_package(self):
        if not self.url:
            return
        self.install_failed = True
        try:
            install_package(self.url, self.folder, on_download=lambda: Thread(
                target=partial(
                    self.on_download, 'precise training exe'
                ), daemon=True
            ).start())
            install_package(
                self.model_url, self.folder,
                on_download=lambda: Thread(
                    target=partial(
                        self.on_download, 'precise training model'
                    ), daemon=True
                ).start()
            )
            _thread.start_new_thread(self.download_sounds, ())
            self.install_failed = False
        finally:
            self.install_complete.set()

    def has_free_disk_space(self):
        space = (30 * self.settings["channels"] *
                 self.settings["rate"] / 1024 / 1024)
        free_mb = psutil.disk_usage('/')[2] / 1024 / 1024
        return free_mb - space > self.settings["min_free_disk"]

    @intent_file_handler('wake.word.intent')
    def wake_word_intent(self, message):
        if message.data.get("name"):
            name = message.data.get("name")
        else:
            name = self.get_response('witch.wakeword')
        name = name.replace(' ', '-')
        if name == self.config_core.get('listener', {}).get('wake_word').replace(' ', '-'):
            self.train_wake_word_intent(message)
            return
        else:
            self.config(name, message)

    def event(self):
        self.log.info("test schleife")


    @intent_file_handler('train.intent')
    def train_precise(self, message):
        self.log.info("calculating")
        if message.data.get("name"):
            name = message.data.get("name")
            name = name.replace(' ', '-')
            self.calculating_intent(name)
            self.speak_dialog("start.calculating")
            
    @intent_file_handler('train.no.wake.word.intent')
    def train_no_wakeword(self, message):
        if message.data.get("nonumber"):
            self.settings["nowwnr"] = int(message.data.get("nonumber"))
        self.settings["wwnr"] = 0
        self.train_wake_word_intent(message)
               

    @intent_file_handler('train.wake.word.intent')
    def train_wake_word_intent(self, message):
        if message.data.get("number"):
            self.settings["wwnr"] = int(message.data.get("number"))
        if message.data.get("name"):
            name = message.data.get("name")
        else:
            name = self.get_response('witch.wakeword')
            if name is None:
                self.speak_dialog('no')
                return
        name = name.replace(' ', '-')
        if os.path.isdir(self.settings["file_path"]+name):
            if self.ask_yesno("model.available",
                            data={"name": name}) == "yes":
                if os.path.isdir(self.settings["file_path"]+name):
                    rmtree(self.settings["file_path"]+name)
                if os.path.isdir("/tmp/mycroft_wakeword/"):
                    rmtree("/tmp/mycroft_wakeword/")
        if self.settings["wwnr"] >= 1:
            self.speak_dialog("word.wake",
                                data={"name": name, "number":self.settings["wwnr"]})
        else:
            self.speak_dialog("none.wake.word")
            # Throw away any previous recording
        i = 1
        self.halt = False
        source = "/tmp/mycroft_wakeword/"+name
        nopath = "/not-wake-word/"+ self.lang[:2] + "-short/"
        makedirs(source+nopath, exist_ok=True)
        yespath = "/wake-word/"+ self.lang[:2] + "-short/"
        makedirs(source+yespath, exist_ok=True)
        self.new_name = name
        wait_while_speaking()
        ### Record test files to tmp
        while i <= self.settings["wwnr"]+self.settings["nowwnr"]:
            while self.record_process:
                time.sleep(1)
            time.sleep(2)
            if self.halt is True:
                self.remove_event('recognizer_loop:record_end')
                self.remove_event('recognizer_loop:record_begin')
                self.remove_instance_handlers()
                if self.ask_yesno("calculate.anyway") == "yes":
                    self.speak_dialog("start.calculating")
                    self.calculating_intent(self.new_name)
                    return
                else:
                    rmtree(source)
                    self.speak_dialog("no")
                    wait_while_speaking()
                    return
            elif self.halt == "break":
                self.remove_event('recognizer_loop:record_end')
                self.remove_event('recognizer_loop:record_begin')
                self.remove_instance_handlers()
                self.record_file_mover(yespath, nopath, source)
                if self.ask_yesno("calculate.anyway") == "yes":
                    self.speak_dialog("start.calculating")
                    self.calculating_intent(self.new_name)
                else:
                    self.speak_dialog("break")
                    wait_while_speaking()
                    return
            elif self.halt is None:
                shutil.move(self.recordpath + self.recordfile, source+nopath+"not"+self.new_name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                if i <= self.settings["wwnr"]-1:
                    i = i-1
            self.log.info("step number "+str(i))
            if i < self.settings["wwnr"]:
                #play_wav(self.piep)
                self.recordpath = source+yespath
                self.recordfile = str(self.new_name+ "-" + self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
            elif i == self.settings["wwnr"]:
                time.sleep(2)
                self.speak_dialog("none.wake.word")
                wait_while_speaking()
                #play_wav(self.piep)
                self.recordpath = source+nopath
                self.recordfile = str("not"+self.new_name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
            else:
                #play_wav(self.piep)
                self.recordpath = source+nopath
                self.recordfile = str("not"+self.new_name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                #time.sleep(2)
            self.log.info(self.recordfile)
            wait_while_speaking()
            i = i+1
            #play_wav(self.piep).wait()
            if i <= 2:
                self.add_event('recognizer_loop:record_end',
                    self.rec_stop)
                self.add_event('recognizer_loop:record_begin',
                    self.loop)
                self.register_fallback(self.handle_validator, 1)
            self.bus.emit(Message('mycroft.mic.listen'))
            self.start_recording()
                #self.bus.emit(Message('mycroft.volume.unmute',
                #              {"speak_message": False}))
        else:
            self.log.info("end records")
            self.remove_event('recognizer_loop:record_end')
            self.remove_event('recognizer_loop:record_begin')
            self.remove_instance_handlers()
            #### Save wakewords in data folder
            if self.ask_yesno("is.all.ok") == "no":
                rmtree(source)
                return
            wait_while_speaking()
            self.record_file_mover(yespath, nopath, source)
            self.calculating_intent(self.new_name)
            self.speak_dialog("start.calculating")
            #thresh = self.calc_thresh(model_file, samples_raw_folder)
            #print("THRESH:", thresh)

    def record_file_mover(self, yespath, nopath, source):
        #### wake words with 4 test files
        i = 1
        if os.path.isdir(self.settings["file_path"]+self.new_name+"/test"+yespath):
            onlyfiles = next(os.walk(self.settings["file_path"]+self.new_name+"/test"+yespath))
            i = 4 - len(onlyfiles)
        else:
            i = 1
            os.makedirs(self.settings["file_path"]+self.new_name+"/test"+yespath)
        for root, dirs, files in os.walk(source+yespath):
            for f in files:
                filename = os.path.join(root, f)
                if filename.endswith('.wav'):
                    if i <= 4:
                        shutil.move(filename, self.settings["file_path"]+self.new_name+"/test"+yespath+
                                    self.new_name+ "-" + self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                        self.log.info("move file: "+filename)
                        i = i + 1
                    else:
                        makedirs(self.settings["file_path"]+self.new_name+yespath, exist_ok=True)
                        shutil.move(filename, self.settings["file_path"]+self.new_name+yespath+
                                    self.new_name+ "-" + self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                        self.log.info("move file: "+filename)
                        i = i + 1
                #### not wakeword with 4 test files
        i = 1
        if os.path.isdir(self.settings["file_path"]+self.new_name+"/test"+nopath):
            onlyfiles = next(os.walk(self.settings["file_path"]+self.new_name+"/test"+nopath))
            i = 4 - len(onlyfiles)
        else:
            i = 1
            os.makedirs(self.settings["file_path"]+self.new_name+"/test"+nopath)
        for root, dirs, files in os.walk(source+nopath):
            for f in files:
                filename = os.path.join(root, f)
                if filename.endswith('.wav'):
                    if i <= 4:
                        makedirs(self.settings["file_path"]+self.new_name+"/test"+nopath, exist_ok=True)
                        shutil.move(filename, self.settings["file_path"]+self.new_name+"/test"+nopath+
                                    "not"+self.new_name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                        self.log.info("move file: "+filename)
                        i = i + 1
                    else:
                        makedirs(self.settings["file_path"]+self.new_name+nopath, exist_ok=True)
                        shutil.move(filename, self.settings["file_path"]+self.new_name+nopath+
                                    "not"+self.new_name+"-"+ self.lang[:2] +"-"+str(uuid.uuid1())+".wav")
                        self.log.info("move file: "+filename)
                        i = i + 1
    
    def loop(self):
        pass
    
    def handle_validator(self, message):
        self.log.info(self.recordfile)
        if not self.settings["usevalidator"]:
            return True
        msg = message.data.get('utterance')
        self.log.info("match "+str(msg))
        if msg is None:
            #self.remove_event('recognizer_loop:record_end')
            #self.remove_fallback(self.handle_validator)
            self.halt = None
            return True
        if self.voc_match(msg, "stop"):
            self.log.info('Stop')
            self.halt = True
            return True
        elif self.voc_match(msg, "break"):
            self.log.info("break")
            self.halt = "break"
            return True
        elif fuzzy_match(msg, self.new_name) > 0.8:
            self.log.info('skip File to no wakewords')
            self.halt = False
            return True
        else:
            self.halt = None
            return True

    def start_recording(self):
        self.log.info("sart recording")
        self.settings["duration"] = 5  # max recording duration


        if self.has_free_disk_space():
                # Initiate recording
            wait_while_speaking()
            self.start_time = now_local()   # recalc after speaking completes
            makedirs(self.recordpath, exist_ok=True)
            self.record_process = self.record(self.recordpath + self.recordfile,
                                         int(self.settings["duration"]),
                                         self.settings["rate"],
                                         self.settings["channels"])
            self.enclosure.eyes_color(255, 0, 0)  # set color red
            self.last_index = 24
            self.schedule_repeating_event(self.recording_feedback, None, 1,
                                          name='RecordingFeedback')
        else:
            self.speak_dialog("disk.full", wait=True)

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
    def rec_stop(self):
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

    def calculating_intent(self, name):
        self.log.info("calculating")
        self.settings["Name"] = name
        self.download_sounds()
        models_folder = join(self.file_system.path)
        makedirs(models_folder, exist_ok=True)
        model_file = join(self.file_system.path+"/"+name+".net")
        samples_folder = join(self.settings["file_path"], name)
        samples_raw_folder = join(samples_folder, 'wake-word', self.lang[:2]+"-short")
        #samples_raw_folder = join(samples_folder, 'wake-word')
        self.speak_dialog('start.calculating')
        self.log.info("model: "+model_file+" sample folder: "+samples_folder+" raw folder: "+samples_raw_folder)
        self.transfer_train(samples_folder, model_file)

        thresh = self.calc_thresh(model_file, samples_raw_folder)
        print("THRESH:", thresh)
        return True

    def calculating_incremental(self, name, message):
        self.log.info("calculating")
        self.settings["Name"] = name
        self.download_sounds()
        if os.path.isfile(self.file_system.path+"/"+name+".logs/output.txt"):
            os.remove(self.file_system.path+"/"+name+".logs/output.txt")
        call([
            join(self.exe_folder, 'precise-train-incremental'),
            self.file_system.path+"/"+name+".net", self.settings["file_path"]+name
        ])
        return True    

    def download_sounds(self):
        soundfiles = ["baby_5month_babbling", "baby_dissapointed_cry", "baby_working", "bachidylle", "barbecue",
                     "buzzing", "carSound", "complete_summer_storm_with_30_thunder_04of04", "cracking_peanuts", "dishwasher", "dom130807_pd",
                     "dropping_breaking_01", "fasten_your_seat_belt", "firework_part", "german_march_band", "laughter", "laundrette"]
        name = self.settings["Name"]
        if not os.path.isfile(self.file_system.path+"/noises"):
            self.log.info("downloading soundbackup")
            makedirs(self.file_system.path+"/noises/mp3", exist_ok=True)
            for f in soundfiles:
                if not os.path.isfile(self.file_system.path+"/noises/mp3/"+f+".mp3"):
                    self.log.info("downloade file: "+str(f))
                    wget.download('http://downloads.tuxfamily.org/pdsounds/sounds/'+f+'.mp3', 
                                    self.file_system.path+'/noises/mp3/'+f+'.mp3', bar=self.bar_custom)
        #onlyfiles = next(os.walk(self.settings["file_path"]+name+"/not-wake-word/noises"))[2]
        #if len(onlyfiles) <= 30:
        makedirs(self.file_system.path+"/noises/noises", exist_ok=True)  
        onlyfiles = next(os.walk(self.file_system.path+"/noises/noises"))[2]
        if len(onlyfiles) <= 15:
            folder = self.file_system.path+"/noises/mp3/"
            fileformat = '.mp3'
            for root, dirs, files in os.walk(folder):
                for f in files:
                    filename = os.path.join(root, f)
                    if filename.endswith(fileformat):
                        self.log.info("Filename: "+filename)
                        soundfile = filename.replace(fileformat, '').replace(folder, '')
                        # convert and shorten files to 5 s
                        call(["ffmpeg -i "+filename+" -acodec pcm_s16le -t 5 -ar 16000 -ac 1 -f wav "+
                            self.file_system.path+"/noises/noises/"+soundfile+".wav"],
                            preexec_fn=os.setsid, shell=True)
                        self.log.info("extratct: "+filename)
            self.speak_dialog("download.success")
        makedirs(self.settings["file_path"]+name+"/not-wake-word", exist_ok=True)
        self.noise_folder = self.file_system.path+"/noises/noises/"

    def bar_custom(self, current, total, width=80):
        self.log.info("Downloading: %d%% [%d / %d] bytes" % (current / total * 100, current, total))

    def precise_con(self, name, message):
        self.log.info("precise: start convert to .pb")
        call([
            join(self.exe_folder, 'precise-convert'),
            "-o "+self.file_system.path+"/"+name+".pb", self.file_system.path+"/"+name+".net"
        ])
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
        if self.ask_yesno('old.or.new') == "yes":
            ipath = self.settings["sell_path"]
        else:
            ipath = self.settings["file_path"]+name+"/wake-word/"+self.lang[:2]+"-short/"
        if os.path.isdir(ipath):
            onlyfiles = next(os.walk(ipath))[2]
            if len(onlyfiles) <= self.settings["improve"]:
                selling = len(onlyfiles)
            else:
                selling = self.settings["improve"]
            if int(selling) >= 1:
                self.speak_dialog('improve', data={'name': name, "selling": selling}, wait=True)
            else:
                ipath = self.settings["file_path"]+name+"/wake-word/"+self.lang[:2]+"-short/"
                onlyfiles = next(os.walk(ipath))[2]
                selling = len(onlyfiles)
                self.speak_dialog('improve', data={'name': name, "selling": selling}, wait=True)
            self.log.info("search wake word in: "+ipath)
            wait_while_speaking()
            for root, dirs, files in os.walk(ipath):
                for f in files:
                    filename = os.path.join(root, f)
                    if filename.endswith('.wav'):
                        if i <= selling:
                            self.log.info("play file")
                            play_wav(filename)
                            wait_while_speaking()
                            #time.sleep(3)
                            sell = self.ask_yesno("ask.sell", data={'i': i})
                            wait_while_speaking()
                            i = i+1
                            path = None
                            if sell == "yes":
                                path = self.settings["file_path"]+name+"/wake-word/"+self.lang[:2]+"-short/"
                            elif sell == "no":
                                path = self.settings["file_path"]+name+"/not-wake-word/"+self.lang[:2]+"-short-not/"
                            if not path is None:
                                makedirs(path, exist_ok=True)
                                file = path+name+"-"+self.lang[:2]+"-"+str(uuid.uuid1())+".wav"
                                shutil.move(filename, file)
                                self.log.info("move File: "+file)
                            else:
                                os.remove(filename)
            else:
                self.speak_dialog('improve.no.file', data={'name': name})
        else:
            self.speak_dialog('improve.no.file', data={'name': name})

    @intent_file_handler('upload.intent')
    def upload_intent(self, message):
        if not self.settings.get('localgit') or not self.settings.get('gitpass') or not self.settings.get('gitmail'):
            self.speak_dialog('no.login')
            return

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
        if not os.path.isdir(self.precisefolder):
            self.speak_dialog("download.started")
            self.log.info("Downloading Precise Comunity Data")
            repo = git.Repo.clone_from(self.settings["repo"], self.precisefolder)
        else:
            self.log.info("pull Precise Comunity Data")
            repo = git.Repo.init(self.precisefolder)
        repo.config_writer().set_value("user", "name", self.settings.get('localgit')).release()
        repo.config_writer().set_value("user", "email", self.settings.get('gitmail')).release()
        repo.config_writer().set_value("user", "password", self.settings.get('gitpass')).release()
        self.log.info(self.precisefolder)

    def prepaire_repo(self, name):
        name = name.replace('-', '').replace(' ', '')
        ##### Model Files
        self.log.info("make repo ready vor upload")
        presiceversion = linecache.getline(self.file_system.path + "/precise/mycroft_precise.egg-info/PKG-INFO", 3).replace('Version: ', '')[:5]
        modelzip = self.precisefolder+"/"+name+"/models/"+name+"-"+self.lang[:3]+presiceversion+"-"+time.strftime("%Y%m%d")+"-"+self.settings.get('localgit')+".tar.gz"
        makedirs(self.precisefolder+"/"+name+"/models/", exist_ok=True)
        tar = tarfile.open(modelzip, "w:gz")
        for nams in [self.file_system.path+"/"+name+".pb", self.file_system.path+"/"+name+".pbtxt",
                    self.file_system.path+"/"+name+".pb.params"]:
            tar.add(nams)
        #### calculating info
        traininfo = linecache.getline(self.file_system.path+"/"+name+".logs/output.txt", 2)
        #### generate Readme.md
        readmefile = self.precisefolder+"/"+name+"/models/README.md"
        file = open(readmefile, "a")
        if not os.path.isfile(readmefile):
            file.write("# "+name+"\n")
        file.write("\n### "+name+"-"+self.lang[:3]+time.strftime("%Y%m%d")+"\n")
        file.write(presiceversion+" "+traininfo[:1]+". Use Public Domain Sounds Backup: http://downloads.tuxfamily.org/pdsounds/sounds/"+
                    ", automatically generated by wakeword trainer skill \n")
        file.close()

        ###### licenses
        licensefile = self.precisefolder+"/licenses/license-"+time.strftime("%Y%m%d")+"-"+self.settings.get('localgit')+".txt"
        fobj_in = open(self.precisefolder+"/licenses/license-template.txt", "r")
        fobj_out = open(licensefile, "w")
        for line in fobj_in:
            line = line.replace("I, [author name]", "I, "+self.settings.get('localgit')+
            ' (https://github.com/'+self.settings.get('localgit')+')')
            line = line.replace("/file/name/1", "automatically generated by gras64 wakeword trainer skill").replace("/file/name/2", "")
            fobj_out.write(str(line))
        modelzipfile = modelzip.replace(self.precisefolder+"/", "")
        fobj_out.write(modelzipfile+"\n")
        for root, dirs, files in os.walk(self.precisefolder+"/"+name+"/"+self.lang[:2]):
            for f in files:
                filename = os.path.join(root, f)
                self.log.info("filename: "+filename)
                if filename.endswith('.wav'):
                    filename = filename.replace(self.precisefolder, "")
                    fobj_out.write(filename+"\n")
        fobj_in.close()
        fobj_out.close()

        ##### Copy all wav file
        if not self.settings["onlyPrecise"]:
            source = self.settings["file_path"]+name+"/wake-word/"+self.lang[:2]+"-short/"
            destination = self.precisefolder+"/"+name+"/"+self.lang+"/"
            makedirs(destination, exist_ok=True)
            fobj_out = open(licensefile, "a")
            for filename in os.listdir(source):
                if filename.endswith('.wav'):
                    shutil.copy(source + filename, destination)
                    fobj_out.write("/"+name+"/"+self.lang[:2]+"/"+filename+"\n")
            source = self.settings["file_path"]+name+"/test/wake-word/"+self.lang[:2]+"-short/"
            for filename in os.listdir(source):
                if filename.endswith('.wav'):
                    shutil.copy(source + filename, destination)
                    fobj_out.write("/"+name+"/"+self.lang[:2]+"/"+filename+"\n")
            fobj_out.close()

    def git_upload(self, name):
        self.log.info("start with upload "+name)
        repo = git.Repo.init(self.precisefolder)
        extern = ("https://"+self.settings.get('localgit')+":"+self.settings.get('gitpass')+
                "@github.com/"+self.settings.get('localgit')+"/Precise-Community-Data")
        g = Github(self.settings.get('localgit'), self.settings.get('gitpass'))

        user = g.get_user()
        #self.user = str()
        repo_name = ('Precise-Community-Data')
        try:
            #repo = user.create_repo(repo_name)
            self.log.info("create repo")
        except GithubException as e:
            if e.status == 422:
                raise GithubRepoExists(repo_name) from e
            raise
        try:
            repo.git.remote('rename', 'origin', 'upstream')
            repo.git.remote('add', 'origin', extern)
            #repo.git.remote('set-url', '--add', 'origin', self.settings["repo"])
        except:
            self.log.info("Repo exist")
        #repo.pull()
        #repo.git.remote('set-url', '--add', 'origin', self.settings["repo"])
        repo.index.add(["licenses"])
        repo.index.add([name])
        repo.index.commit("Files automatically generated by gras64 wakeword trainer skill")
        call(['git', 'push', '-u', 'origin', 'master'], cwd='/home/pi/.mycroft/skills/WakeWord/Precise-Community-Data')
        #repo.git.request-pull(self.settings["repo"])
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
                self.speak_dialog("disk.full")
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

    def calc_thresh(self, model_file, samples_folder):
        from precise_runner import PreciseEngine
        engine = PreciseEngine(self.engine_exe, model_file, self.chunk_size)
        engine.start()

        all_max = []
        for sample_file in glob(join(samples_folder, '*.wav')):
            self.log.info("samplefile "+sample_file)
            with wave.open(sample_file, 'r') as wr:
                frames = wr.readframes(wr.getnframes() - 1)
            chop = len(frames) % self.chunk_size
            max_pred = float('-inf')
            for i in range(10): 
                engine.get_prediction(b'\0' * self.chunk_size)
            for pos in range(chop + self.chunk_size, len(frames) + 1,
                             self.chunk_size):
                pred = engine.get_prediction(frames[pos - self.chunk_size:pos])
                max_pred = max(max_pred, pred)
            print('MAX PRED:', max_pred)
            all_max.append(max_pred)
        av_max = sum(all_max) / len(all_max)
        stddev = sqrt(sum([(i - av_max) ** 2 for i in all_max]))
        good_max = [i for i in all_max if i > av_max - stddev]
        good_av = sum(good_max) / len(good_max)
        stddev = sqrt(sum([(i - good_av) ** 2 for i in good_max]))
        thresh = good_av - stddev
        return thresh

    def transfer_train(self, samples_folder, model_file):
        noised_folder = mkdtemp()
        wake_word_folder = join(noised_folder, 'wake-word')
        not_wake_word_folder = join(noised_folder, 'not-wake-word')
        makedirs(wake_word_folder, exist_ok=True)
        makedirs(not_wake_word_folder, exist_ok=True)
        call([
            join(self.exe_folder, 'precise-add-noise'),
            samples_folder, self.noise_folder, wake_word_folder,
            '-if', '10', '-nl', '0.0', '-nh', '0.4'
        ])
        self.log.info("add noise wakeword")
        call([
            join(self.exe_folder, 'precise-add-noise'),
            self.noise_folder, self.noise_folder, not_wake_word_folder,
            '-if', '10', '-nl', '0.0', '-nh', '0.4'
        ])
        self.log.info("add not noise wakeword "+ self.model_file+" "+model_file)
        shutil.copy(self.model_file, model_file)

        call([
            join(self.exe_folder, 'precise-train'),
            model_file, noised_folder,
            '-e', '1', '-b', '4096',
        ])


    def shutdown(self):
        super(WakeWord, self).shutdown()
        self.stop_process(self.recording_server)
        self.remove_event('recognizer_loop:record_end')
        self.remove_event('recognizer_loop:record_begin')
        self.remove_instance_handlers()
        self.settings.update

def create_skill():
    return WakeWord()
