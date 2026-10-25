# Robot and ontology source inventory

Retrieved 2026-10-25. Machine-readable pins live in
[`knowledge-graphs/manifests/sources.yaml`](../../knowledge-graphs/manifests/sources.yaml).
File hashes are in `sources.lock.json`. Upstream trees are never committed; `jazari fetch`
recreates them.

## Summary

| Source | Pinned revision | License | Status in JAZARI |
|---|---|---|---|
| [unitreerobotics/unitree_ros](https://github.com/unitreerobotics/unitree_ros) | `15ebe53f4cd77e7d745ae83b9d7ff90e685e8998` (2026-10-23) | BSD-3-Clause | **Ingested** (G1 29-DoF rev 1.0, URDF + MJCF + 2 docs) |
| [srfiorini/IEEE1872-owl](https://github.com/srfiorini/IEEE1872-owl) | `ffb6613350b28c3a710f8daf2a1e9e953ded7ed8` | CC-BY-4.0 (declared in OWL `dc:rights`; no LICENSE file) | **Loaded** (cora, cora-bare, corax, rparts, sumo-cora, pos, annotation) |
| [berkeley-humanoids/lite_description](https://github.com/berkeley-humanoids/lite_description) | `e582f6b27e2f4954d914f5db9d46e6dd409c74fb` | MIT | **Ingested** (`lite` URDF + MJCF; `lite_biped` Xacro + MJCF) |
| [HybridRobotics/Berkeley-Humanoid-Lite](https://github.com/HybridRobotics/Berkeley-Humanoid-Lite) | `984741a3623c93b0583ccfdc479f1f8b1c4d900e` | MIT | Not used: the V2 descriptions live in `lite_description` |
| [google-deepmind/mujoco_menagerie `aloha/`](https://github.com/google-deepmind/mujoco_menagerie/tree/main/aloha) | `f3b6013629c7b94f8ee93fd977b161fa8350f9bc` | `aloha/LICENSE`: BSD-3-Clause, © 2023 Trossen Robotics (Menagerie licenses each model separately) | **Ingested** (`aloha.xml` + included actuator file) |

## Unitree G1

**Selected configuration: `g1_29dof_rev_1_0`** (`mode_machine` 5).

The upstream README lists 23 G1 description variants: modes 10–18, revision-1.0 variants,
hand add-ons (Dex3, Inspire DFQ/FTP, Dex1), a dual-arm variant, `g1_pl` (G1+, 31 DoF) and
four deprecated files. `g1_29dof_rev_1_0` was chosen because it is:

- marked *Up-to-date* and matches the revision-1.0 hardware;
- described in **both** URDF and MJCF;
- the full core body (6×2 leg, 3 waist, 7×2 arm) without optional hands, so later
  configurations can extend it cleanly.

Values from other variants are never mixed in: a variant is one `jz:RobotConfiguration`
with its own files.

What each format actually states for this variant (from the parsers, not assumed):

| Aspect | URDF `g1_29dof_rev_1_0.urdf` | MJCF `g1_29dof_rev_1_0.xml` |
|---|---|---|
| Links / bodies | 39 links | 30 bodies (fixed links merged into geoms) |
| Joints | 38: 29 revolute, 9 fixed | 30: 29 hinge, 1 free |
| Floating base | commented out | `floating_base_joint` type `free` |
| Joint limits | lower, upper, effort, velocity | range, actuatorfrcrange (no velocity) |
| Actuators | none (URDF has no actuator element) | 29 `<motor>` elements, no gear stated |
| Sensors | frames only (`imu_in_*`, `d435_link`, `mid360_link`) | 2 gyros + 2 accelerometers on IMU sites |
| Masses | 35 links with mass; 4 frame links without | all 30 bodies; same sum, 33.3411 kg |

**Upstream inconsistencies found by validation:** the effort limit of the ankle pitch/roll
joints (left and right) and of the waist roll/pitch joints is **35 N·m in the URDF but
50 N·m in the MJCF**. `motor_info.md` lists 41 N·m for the ankle motor type and 60 N·m for
waist roll/pitch, and the README says `g1_pl` raises those values. JAZARI reports all of
these values side by side with their sources and does not pick one.

Documents indexed: `robots/g1_description/README.md` (variant table), `motor_info.md`
(motor types, effort and velocity). Meshes (`*.STL`) are excluded from the fetch until 3D
visualisation (M5).

## Berkeley Humanoid Lite

The upstream README lists six V2 variants: `lite` (full body, 1-DoF waist, 72 DoF),
`lite_pro` (3-DoF waist, 74), `lite_biped` (legs, 14), `lite_biped_debug`, `lite_dummy`
(V1 upper body, 17) and `lite_bimanual` (arms, 14). The URDF and MJCF of each are generated
from the Onshape CAD.

**Baseline: `lite`.** This is the complete humanoid and the variant comparable with the G1.
**Second configuration: `lite_biped`.** Only this variant's Xacro has a hardware
`ros2_control` description. It is kept as its own `jz:RobotConfiguration` and never
mixed with `lite`.

| Aspect | `lite` URDF | `lite` MJCF | `lite_biped` Xacro (expanded) | `lite_biped` MJCF |
|---|---|---|---|---|
| Links / bodies | 73 | 73 | 17 | 16 |
| Joints | 72 revolute | 72 hinge + pelvis welded to world | 14 revolute + 2 fixed | 14 hinge + 1 free |
| Hands | 40 finger joints (5 fingers × 4 joints × 2) | same, 40 position actuators | — | — |
| Root | `pelvis`, no floating joint | `pelvis` body without joint (fixed to world) | `base_link` → `pelvis` | `pelvis` free joint |
| Actuators | none (URDF) | 72 `<position>` with `forcerange` | 14 `ros2_control` joints: RobStride model, CAN id, torque and current limit | 14 `<position>` |
| Sensors | — | — | IMU only with `sim_mujoco` or real hardware (not with default args) | gyro, accelerometer, velocimeter, framequat, framepos |

Actuator models in `lite_biped`: 6× rs-06 (hip pitch/roll, knee), 2× rs-02 (hip yaw), 4×
rs-00 (ankle yaw and pitch), 2× rs-05 (ankle roll). The ankle pitch is driven through a
four-bar linkage, whose raw parameters are stored as written; the source states no units
for them. Torque limits in the Xacro match the MJCF `forcerange`. Current limits exist only
in the Xacro.

**Xacro expansion check:** expanding `lite.urdf.xacro` with JAZARI's sandboxed expander
reproduces every joint of the generated `lite.urdf` (parent, child, type, limits, axis)
and every link mass. The only difference is the extra `base_link_to_pelvis` fixed joint in
the Xacro. This is an automated test.

## ALOHA 2

MuJoCo Menagerie `aloha/` is a simplified bimanual MJCF derived from the ViperX 300 6DOF
model. Its README documents system-identified actuator gains, damping and friction, a
position-controlled gripper with an equality constraint, and 4 cameras: overhead,
worm's-eye, and two wrist cameras matched to RealSense D405 intrinsics. ALOHA 2 is modelled
as a **bimanual manipulator**, not a humanoid.

What `aloha.xml` (with its `<include>`d `joint_position_actuators.xml`) states:

- 2 separate kinematic trees (`left/base_link`, `right/base_link`), each welded to the world
- per arm: 6 revolute joints (waist, shoulder, elbow, forearm_roll, wrist_angle,
  wrist_rotate) and 2 prismatic finger joints
- 2 joint couplings (`<equality><joint>`, polycoef `0 1 0 0 0`): each right finger follows
  its left finger. So there are 16 articulated DoF but 14 independent DoF
- 14 `<position>` actuators with class-default gains (`kp`) and control ranges. No motor
  model or gear ratio is stated
- 4 cameras in `aloha.xml`: two wrist cameras on the gripper bases, and two world-fixed
  viewpoints (`teleoperator_pov`, `collaborator_pov`). The overhead and worm's-eye cameras
  are in `scene.xml`, which is environment and is not ingested.

## Redistribution policy

- Upstream robot files are fetched by script and are not committed.
- The generated knowledge graphs (`knowledge-graphs/generated/`) contain extracted facts
  and identifiers derived from BSD-3-Clause sources. They are reproducible and kept out of
  git. If they are published later, they must keep the upstream copyright notices.
- No IEEE standard text, internal Dassault Systèmes material or confidential documents are
  used or included.
