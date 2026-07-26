# <img src='./icon.png' card_color='#40DBB0' width='50' height='50' style='vertical-align:bottom'/> Parrot

Turn OpenVoiceOS into an echoing parrot!

Make OVOS repeat whatever you want — your own recent speech, its own recent
speech, or anything you tell it to say — and, on request, keep echoing back
everything it hears until told to stop.

## About

This skill offers a few ways to make OVOS repeat things:

- **Say it verbatim** — ask OVOS to speak any sentence you give it
  ("say Goodnight, Gracie").
- **Repeat what you just said** — OVOS replays your own last recognized
  utterance (with a different reply if it was more than two minutes ago).
- **Repeat what it just said** — OVOS replays the last thing it spoke.
- **"Did you hear me?"** — OVOS confirms whether it heard you in the last
  minute and, if so, repeats it back; otherwise it apologizes and asks you
  to repeat yourself.
- **Parrot mode** — say "start parrot" and OVOS echoes back every utterance
  it hears, verbatim, until you say "stop parrot". While parrot mode is
  active on the main device session, a GUI page is shown as well.

The skill runs fully offline — it needs no internet, network, or GUI to
function.

## Examples

* "say Goodnight, Gracie"
* "repeat Once upon a midnight dreary, while I pondered, weak and weary, Over
  many a quaint and curious volume of forgotten lore"
* "speak I can say anything you'd like!"
* "Repeat what you just said"
* "Repeat that"
* "Can you repeat that?"
* "What did I just say?"
* "Tell me what I just said."
* "Did you hear that?"
* "start parrot"
* "hello" → "hello"
* "stop parrot"

## Installation

```bash
pip install ovos-skill-parrot
```

Or install it like any other OVOS skill through your skill manager /
`ovos-core` skill installer.

## Supported languages

English (en-US) is the primary locale; community translations also exist for
Catalan (ca-ES), Galician (gl-ES), Italian (it-IT), Brazilian and European
Portuguese (pt-BR, pt-PT), Spanish (es-ES), Basque (eu-ES), Danish (da-DK),
German (de-DE), Persian (fa-IR), and French (fr-FR).

## Credits

- JarbasAl
- [MatthewScholefield/skill-repeat-recent](https://github.com/MatthewScholefield/skill-repeat-recent) — origin of the repeat / "did you hear me" intents

## Category

**Entertainment**
