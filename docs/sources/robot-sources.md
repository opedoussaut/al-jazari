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
| [berkeley-humanoids/lite_description](https://github.com/berkeley-humanoids/lite_description) | `e582f6b27e2f4954d914f5db9d46e6dd409c74fb` (candidate) | MIT | Planned M3 |
| [HybridRobotics/Berkeley-Humanoid-Lite](https://github.com/HybridRobotics/Berkeley-Humanoid-Lite) | `984741a3623c93b0583ccfdc479f1f8b1c4d900e` (candidate) | MIT | Planned M3 |
| [google-deepmind/mujoco_menagerie `aloha/`](https://github.com/google-deepmind/mujoco_menagerie/tree/main/aloha) | `f3b6013629c7b94f8ee93fd977b161fa8350f9bc` (candidate) | `aloha/LICENSE`: BSD-3-Clause, © 2023 Trossen Robotics (repo-level: per-model licenses) | Planned M3 |

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

## Berkeley Humanoid Lite (planned M3)

`lite_description` provides URDF/MJCF and several configurations (full humanoid, biped,
bimanual). Baseline selection and variant identity will be recorded in the manifest, the
same way as for the G1. Xacro expansion support is required.

## ALOHA 2 (planned M3)

MuJoCo Menagerie `aloha/` is a simplified bimanual MJCF derived from the ViperX 300 6DOF
model. Its README documents system-identified actuator gains, damping and friction, a
position-controlled linear gripper actuator with an equality constraint, and 4 cameras
(overhead, worm's-eye, two wrist cameras matched to RealSense D405 intrinsics). It is a
bimanual manipulation platform and will be modelled as such, not as a humanoid.

## Redistribution policy

- Upstream robot files are fetched by script and are not committed.
- The generated knowledge graphs (`knowledge-graphs/generated/`) contain extracted facts
  and identifiers derived from BSD-3-Clause sources. They are reproducible and kept out of
  git. If they are published later, they must keep the upstream copyright notices.
- No IEEE standard text, internal Dassault Systèmes material or confidential documents are
  used or included.
