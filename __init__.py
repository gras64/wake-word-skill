from mycroft import MycroftSkill, intent_file_handler


class WakeWord(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    @intent_file_handler('word.wake.intent')
    def handle_word_wake(self, message):
        self.speak_dialog('word.wake')


def create_skill():
    return WakeWord()

