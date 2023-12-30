from time import monotonic

from ovos_bus_client.session import SessionManager, Session
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills import OVOSSkill


class ParrotSkill(OVOSSkill):

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(
            internet_before_load=False,
            network_before_load=False,
            gui_before_load=False,
            requires_internet=False,
            requires_network=False,
            requires_gui=False,
            no_internet_fallback=True,
            no_network_fallback=True,
            no_gui_fallback=True
        )

    def initialize(self):
        self.parrot_sessions = {}
        # events used in intents from
        # https://github.com/MatthewScholefield/skill-repeat-recent
        self.add_event('recognizer_loop:utterance', self.on_utterance)
        self.add_event('speak', self.on_speak)

    def on_utterance(self, message):
        utt = message.data['utterances'][0]
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            self.parrot_sessions[sess.session_id] = {"current_stt": "",
                                                     "parrot": False,
                                                     "tts_timestamp": -1,
                                                     "stt_timestamp": -1}
        self.parrot_sessions[sess.session_id]["prev_stt"] = self.parrot_sessions[sess.session_id]["current_stt"]
        self.parrot_sessions[sess.session_id]["current_stt"] = utt
        self.parrot_sessions[sess.session_id]["stt_timestamp"] = monotonic()

    def on_speak(self, message):
        utt = message.data['utterance']
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            self.parrot_sessions[sess.session_id] = {"current_stt": "",
                                                     "parrot": False,
                                                     "tts_timestamp": -1,
                                                     "stt_timestamp": -1}
        self.parrot_sessions[sess.session_id]["prev_tts"] = utt
        self.parrot_sessions[sess.session_id]["tts_timestamp"] = monotonic()

    # Intents
    @intent_handler("speak.intent")
    def handle_speak(self, message):
        # replaces https://github.com/MycroftAI/skill-speak
        repeat = message.data.get("sentence", "").strip()
        self.speak(repeat, wait=True)

    @intent_handler('repeat.tts.intent')
    def handle_repeat_tts(self, message):
        # replaces https://github.com/MatthewScholefield/skill-repeat-recent
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            utt = self.translate('nothing')
        else:
            utt = self.parrot_sessions[sess.session_id]["prev_tts"]

        self.speak_dialog('repeat.tts', {"tts": utt})

    @intent_handler('repeat.stt.intent')
    def handle_repeat_stt(self, message):
        # replaces https://github.com/MatthewScholefield/skill-repeat-recent
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            utt = self.translate('nothing')
            ts = 0
        else:
            utt = self.parrot_sessions[sess.session_id]["prev_stt"]
            ts = self.parrot_sessions[sess.session_id]["stt_timestamp"]

        if monotonic() - ts > 120:
            self.speak_dialog('repeat.stt.old', {"stt": utt})
        else:
            self.speak_dialog('repeat.stt', {"stt": utt})

    @intent_handler('did.you.hear.me.intent')
    def handle_did_you_hear_me(self, message):
        # replaces https://github.com/MatthewScholefield/skill-repeat-recent
        sess = SessionManager.get(message)
        if sess.session_id in self.parrot_sessions:
            ts = self.parrot_sessions[sess.session_id]["stt_timestamp"]
            utt = self.parrot_sessions[sess.session_id]["prev_stt"]
            if ts > 0 and utt and monotonic() - ts < 60:  # less than 1 minute ago
                self.speak_dialog('did.hear')
                self.speak_dialog('repeat.stt', {"stt": utt})
                return
        self.speak_dialog('did.not.hear')
        self.speak_dialog('please.repeat', expect_response=True)

    # continuous conversation
    @intent_handler("start_parrot.intent")
    def handle_start_parrot_intent(self, message):
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            self.parrot_sessions[sess.session_id] = {"current_stt": "",
                                                     "parrot": False,
                                                     "tts_timestamp": -1,
                                                     "stt_timestamp": -1}

        self.parrot_sessions[sess.session_id]["parrot"] = True
        self.speak_dialog("parrot_start", expect_response=True)
        if sess.session_id == "default":
            self.gui["running"] = True
            self.gui.show_page("parrot.qml", override_idle=True)

    @intent_handler("stop_parrot.intent")
    def handle_stop_parrot_intent(self, message):
        sess = SessionManager.get(message)
        if sess.session_id in self.parrot_sessions and \
                self.parrot_sessions[sess.session_id]["parrot"]:
            self.stop_session(sess)
        else:
            self.speak_dialog("not_parroting")

    def converse(self, message):
        utterances = message.data["utterances"]
        sess = SessionManager.get(message)
        if sess.session_id in self.parrot_sessions and \
                self.parrot_sessions[sess.session_id]["parrot"]:
            # check if stop intent will trigger
            if self.voc_match(utterances[0], "StopKeyword") and \
                    self.voc_match(utterances[0], "ParrotKeyword"):
                self.handle_stop_parrot_intent(message)
                return True
            # if not parrot utterance back
            self.speak(utterances[0], expect_response=True)
            return True
        return False

    def stop_session(self, session: Session):
        if session.session_id in self.parrot_sessions and\
                self.parrot_sessions[session.session_id]["parrot"]:
            self.parrot_sessions[session.session_id]["parrot"] = False
            self.speak_dialog("parrot_stop")
        if session.session_id == "default":
            self.gui["running"] = False
            self.gui.release()

    def stop(self):
        sess = SessionManager.get()
        if sess.session_id in self.parrot_sessions and \
                self.parrot_sessions[sess.session_id]["parrot"]:
            self.stop_session(sess)
            return True
        return False
