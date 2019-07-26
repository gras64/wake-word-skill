from mycroft import MycroftSkill, intent_file_handler
from mycroft.util import record, play_wav


class WakeWord(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        self.play_process = None
        self.record_process = None
        self.start_time = 0
        self.last_index = 24  # index of last pixel in countdowns

        self.settings["min_free_disk"] = 100  # min mb to leave free on disk
        self.settings["rate"] = 16000  # sample rate, hertz
        self.settings["channels"] = 1  # recording channels (1 = mono)
        self.settings["file_path"] = self.file_system.path + "/recordings"
        self.settings["duration"] = -1  # default = unknown

    @intent_file_handler('word.wake.intent')
    def handle_word_wake(self, message):
        self.speak_dialog('word.wake')



    def start_recording(self, message)
                # Initiate recording
            wait_while_speaking()
            self.start_time = now_local()   # recalc after speaking completes
            self.record_process = record(self.settings["file_path"],
                                         int(self.settings["duration"]),
                                         self.settings["rate"],
                                         self.settings["channels"])
            self.enclosure.eyes_color(255, 0, 0)  # set color red
            self.last_index = 24
            self.schedule_repeating_event(self.recording_feedback, None, 1,
                                          name='RecordingFeedback')
        else:
            self.speak_dialog("audio.record.disk.full")

    def recording_feedback(self, message):
        if not self.record_process:
            self.end_recording()
            return

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


def create_skill():
    return WakeWord()

