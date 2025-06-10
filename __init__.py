from time import monotonic
from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager, Session
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.converse import ConversationalSkill


class ParrotSkill(ConversationalSkill):

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
            utt = self.resources.render_dialog('nothing')
        else:
            utt = self.parrot_sessions[sess.session_id]["prev_tts"]

        self.speak_dialog('repeat.tts', {"tts": utt})

    @intent_handler('repeat.stt.intent')
    def handle_repeat_stt(self, message):
        # replaces https://github.com/MatthewScholefield/skill-repeat-recent
        sess = SessionManager.get(message)
        if sess.session_id not in self.parrot_sessions:
            utt = self.resources.render_dialog('nothing')
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
        self.speak_dialog("parrot_start")
        if sess.session_id == "default":
            self.gui["running"] = True
            self.gui.show_page("parrot", override_idle=True)
            # TODO - enable hybrid listening mode while parrot is on

    @intent_handler("stop_parrot.intent")
    def handle_stop_parrot_intent(self, message):
        sess = SessionManager.get(message)
        if sess.session_id in self.parrot_sessions and \
                self.parrot_sessions[sess.session_id]["parrot"]:
            self.stop_session(sess)
        else:
            self.speak_dialog("not_parroting")

    def can_converse(self, message: Message) -> bool:
        """
        Determines if the skill can handle the given utterances in the specified language in the converse method.

        Override this method to implement custom logic for assessing whether the skill is capable of answering a query.

        Returns:
            True if the skill can handle the query during converse; otherwise, False.
        """
        sess = SessionManager.get(message)
        return sess.session_id in self.parrot_sessions and \
                self.parrot_sessions[sess.session_id]["parrot"]

    def converse(self, message):
        utterances = message.data["utterances"]
        # check if stop intent
        if self.voc_match(utterances[0], "StopKeyword") and \
                self.voc_match(utterances[0], "ParrotKeyword"):
            self.handle_stop_parrot_intent(message)
        else:  # else parrot utterance back
            self.speak(utterances[0])

    def handle_deactivate(self, message):
        """
        Called when this skill is no longer considered active by the intent
        service; converse method will not be called until skill is active again.
        """
        sess = SessionManager.get(message)
        self.stop_session(sess)

    def can_stop(self, message: Message) -> bool:
        return self.can_converse(message)  # same logic

    def stop_session(self, session: Session):
        if session.session_id in self.parrot_sessions and \
                self.parrot_sessions[session.session_id]["parrot"]:
            self.parrot_sessions[session.session_id]["parrot"] = False
            self.speak_dialog("parrot_stop")
            if session.session_id == "default":
                self.gui["running"] = False
                self.gui.release()
            return True
        return False