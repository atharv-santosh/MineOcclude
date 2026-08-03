raw_actions.jsonl is in Person A's official raw format (keyboard.keys +
mouse.dx/dy/buttons), verified drop-in against A's golden action matrix
(tests/data/test_person_a_action_compat.py).

There is intentionally NO token file in this bundle: MineWorld's 11 action
tokens are Person A's output. A generates them from raw_actions.jsonl via
convert_action (vocabulary_offset=8192; roles bos/camera_pitch/camera_yaw/
hotbar/forward_back/left_right/sprint_sneak/use_attack/jump/drop_pick/eos).
Person C does not ship tokens — the token vocabulary is A-owned.
