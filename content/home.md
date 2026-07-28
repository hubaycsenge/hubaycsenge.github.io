---
name: Csenge Hubay
tagline: PhD researcher — emotion modelling for social robots
affiliation: ""            # e.g. "Doctoral School of Informatics, …" — fill in or leave blank to hide
email: csengehubay@gmail.com
github: hubaycsenge
scholar: ""                # optional Google Scholar URL
orcid: ""                  # optional ORCID URL
---

## About

I build **emotional engines for social robots**, in the *ethorobotics* tradition:
the view that a social robot should be treated as a species adapted to its own
niche rather than as an imitation of a human being.

My work sits on a specific bet. Most affective computing in human–robot
interaction models only the human. I am building an engine that fuses **two**
input streams — the perceived affective state of the person, and the robot's own
internal state: battery, sensor health, motor load — and generates behaviour
from their combination. Behaviour is modelled on **dog–human interaction**, not
by imitation but by functional analogy: dog ethology supplies legible social
primitives, which are re-expressed in whatever embodiment is available.

The behaviour layer is learnt rather than hand-authored — reinforcement learning
over an ethologically derived action set, with behaviour trees executing the
primitives — and the target is validation **on human subjects in real
environments**, not in the lab.

## Research themes

- **Ethorobotics and function-orientedness** — why robot form should follow
  function, and what the uncanny valley looks like when reread as a problem of
  agent categorisation.
- **Emotion attribution to artificial agents** — people ascribe emotions to
  robots spontaneously and act on the ascription; the affective layer is
  licensed by that, and undermined when it misreads.
- **Grounding models** — Panksepp's neural affective systems against Plutchik's
  adaptive continuous states, and the case for a hybrid.
- **Perception-to-affect** — reading affect from body pose and multimodal
  signals in real time. This is the open gap, in the field as much as in the
  thesis.
- **Learning the behaviour layer** — reward design for an agent whose reward
  signal is partly its own internal state.

## Platform

Experiments run on **Mecanumbot**: a mecanum-drive mobile robot with a Jetson
Orin Nano, lidar and camera, a 17-keypoint body-pose pipeline, a neck and
grabbers, and LED panels used for expressive output. The perception stack fuses
DR-SPAAM person detection with YOLO-pose; the behaviour layer is built on
`py_trees_ros`.
