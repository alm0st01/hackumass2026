# Search mini-bots: pitch brief

Context for planning our HackUMass 2026 pitch and presentation. It covers what the robots do, the
problem they address, statistics we've verified, and what we must not claim. Please help us turn
this into a short elevator pitch, a demo script and slide ideas.

## One-line idea

A group of cheap, small ground robots that run search patterns in parallel. Each one spots a
person with its camera and radios the location back to rescuers, so people spend their time and
energy getting victims out instead of on slow, repetitive searching.

## The problem

1. **Search is a race against time.** In the 1980 southern Italy earthquake, 93.6% of the people
   rescued alive were pulled out within the first 24 hours. 95% of deaths (192 of 202) were among
   trapped people who died before rescuers reached them (De Bruycker et al., 1983, WHO bulletin).
2. **Search costs a lot of human time.** Snohomish County, WA reports more than 1,000 SAR missions
   and more than 47,000 hours since 2016, mostly from volunteers. That's about 47 person-hours
   per mission (a rough average; the total includes some non-wilderness cases). The main
   lost-person research database (ISRID) covers at least 2 million person-hours of searching.
3. **Searchers get worn out.** At the 2021 Surfside condo collapse, crews worked 12-hour shifts
   (midnight to noon, noon to midnight), and one rescuer described getting a few hours of sleep
   between shifts. NIOSH (part of the CDC) warns that mental fatigue over long shifts can "greatly
   increase" emergency workers' risk of injury.

Our argument is that tired people slow down and make more mistakes at the point where speed
matters most. Robots don't get tired, and several can sweep different parts of an area at once.

## What the robot does

- **Hardware:** Raspberry Pi 5 (brain), Logitech USB camera, IMU (BNO055 compass preferred,
  MPU6050 supported), ESP32 motor controller with an L298N driver and an IR distance sensor, and a
  Heltec LoRa radio running Meshtastic.
- **No GPS and no overhead camera.** The robot is placed next to the base, and that spot becomes
  (0, 0). It estimates its position by dead reckoning: heading from the IMU and distance from
  calibrated speed multiplied by driving time. A small Kalman filter combines these and tracks
  how uncertain the estimate is.
- **Search patterns** (standard ones used by real SAR teams):
  - `grid`: back-and-forth tracks that cover a whole area evenly.
  - `sector`: the IAMSAR "VS" pattern around a last-known position; densest coverage at the center.
  - `radial`: spokes out and back from a point, for a quick look in every direction.
- **Detection:** YOLOv8 person detection (and AprilTags as test targets). A target counts as
  found after 5 consecutive frames, which cuts false alarms.
- **Reporting:** on a confirmed find the robot stops and sends a `DETECTION` over the LoRa mesh
  to a laptop base, with its estimated position (for example "x 12.3 m, y 30.1 m from start,
  ±2.4 m"). The message is resent until the base confirms it. Meshtastic doesn't need cell
  service or Wi-Fi.
- **Base commands:** SCAN, RESUME, STOP, HOME (drive back to start). Every heartbeat includes the
  robot's state.
- **Safety:** this runs on the ESP32, not the Pi. Motors stop if the Pi goes quiet for 300 ms
  (crash, freeze, unplugged cable), and the robot won't drive forward into a close obstacle.
  It detours around obstacles and skips a waypoint after 4 blocked attempts so one obstacle can't
  stall the whole search.

## Simulation results (8 runs each, deliberately imperfect robot)

The simulated robot has 10% speed error, wheel slip, ±10% turn error, a 3° compass bias and gyro
drift. The camera is assumed to see 3 m to either side.

| Pattern | Worst position error | Area covered |
|---|---|---|
| sector, 15 m legs | 1.7 m | 74% (best possible for this pattern: 77%) |
| radial, 8 × 15 m | 1.6 m | 76% (best possible: 78%) |
| grid 30×40 m, speed 3% off | 2.8 m | 87% (best possible: 100%) |
| grid 30×40 m, speed 10% off | 5.3 m | 81% |

What this shows: sector and radial stay within about 2 m without GPS, because each leg returns
through the center and errors partly cancel. The grid drifts more, but calibrating the speed
halves its error.

## Framing rules

- **Say "takes over the search sweep," not "replaces rescuers."** A robot can't dig someone out or
  give first aid. The robots handle the tiring, repetitive sweep and call in a person when they
  find someone.
- **State the 93% correctly.** It's "93% of *survivors* were rescued in the first 24 hours," not
  "93% of trapped people die after 24 hours."
- **Don't claim robots have been proven to find victims faster or save rescuer lives.** We
  couldn't find a measured statistic for that, only projected benefits. It's safe to say rescue
  robots have been deployed at about 30 disasters since 9/11 (Robin Murphy's group).
- **Don't use the "135 rescuers died in Mexico City 1985" figure.** It circulates online, but we
  couldn't verify it.
- **Be upfront about limits:** dead-reckoning position drifts over long paths (meters, not
  centimeters), detection range is limited to what the camera sees, and this is a hackathon
  prototype on flat ground, not a rubble-crawling robot. Judges trust a team that knows its
  limits.

## What we want help with

1. A 30-second elevator pitch and a 2–3 minute version.
2. A live demo script. For example: a teammate hides in the room, the base sends SCAN, the robot
   runs a sector pattern, finds them, and the base laptop shows the detection and position.
3. Slide outline: problem → idea → how it works → demo → results → limits and next steps.
4. Likely judge questions with answers (why no GPS? why LoRa? what about rubble? false positives?
   cost per robot? how many robots, and how do they split an area?).
5. Next steps worth mentioning: GPS outdoors, thermal camera, splitting an area across robots
   automatically, mapping finds on a shared map at the base.

## Sources

- De Bruycker et al., "The 1980 earthquake in Southern Italy" (WHO bulletin):
  https://www.iris.unina.it/retrieve/e268a72d-8b54-4c8f-e053-1705fe0a812c/The%201980%20earthquake%201983.pdf
- Pitt Supercourse summary of the same study: https://sites.pitt.edu/~super1/lecture/lec13051/013.htm
- AP, "After an earthquake, how long can trapped victims survive?":
  https://abcnews.com/Technology/wireStory/after-earthquake-long-trapped-victims-survive-134313494
- Snohomish County SAR hours (HeraldNet):
  https://www.heraldnet.com/news/search-and-rescue-enjoy-outdoors-but-think-before-you-hike
- Lost Person Behavior / ISRID: https://www.dbs-sar.com/LPB/Introduction.pdf
- Surfside rescuers (NHPR/NPR):
  https://www.nhpr.org/national/2021-07-11/how-rescue-and-recovery-teams-in-surfside-are-coping
- Champlain Towers response (Fire Engineering):
  https://www.fireengineering.com/technical-rescue/collapse-of-the-champlain-towers-south-condominium-coordinated-response-and-lessons-learned/
- NIOSH traumatic incident stress and fatigue: https://www.cdc.gov/niosh/stress/traumaticincidentstress
- Rescue robots at about 30 disasters (Discover):
  https://www.discovermagazine.com/after-disaster-strikes-a-robot-might-save-your-life-41777
