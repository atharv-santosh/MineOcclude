# Person A â€” MineWorld Pinned Code-Reading Sign-off

## Review source

Official MineWorld repository:
https://github.com/microsoft/mineworld

Pinned Microsoft source revision:
`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

Purpose:
Record the authoritative MineWorld code paths reviewed for Person A Step A0.4.

The goal of this review is to identify which upstream MineWorld behaviors Person A must reuse or test rather than recreating from memory.

---

# 1. mcdataset.py

## File

`mcdataset.py`

## Microsoft revision

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## What this file controls

This file controls MineWorld's action preprocessing and action-token construction.

It defines:

- keyboard-to-action mappings;
- mouse and camera preprocessing;
- camera scaling;
- camera quantization;
- the action vocabulary;
- the exact 11-token action sequence;
- conflicting-action behavior;
- JSONL action-file loading.

## Relevant authoritative symbols

### `MCDataset.json_action_to_env_action`

Converts raw recorded keyboard and mouse JSON into MineWorld's normalized action dictionary.

Important behavior:

- mouse `dy` becomes camera element 0;
- mouse `dx` becomes camera element 1;
- both are multiplied by `CAMERA_SCALER`;
- `CAMERA_SCALER = 360.0 / 2400.0`;
- conflicting movement and action pairs are cancelled.

Conflicting pairs handled by the official implementation include:

- forward + back;
- left + right;
- jump + sneak;
- sprint + sneak;
- attack + use.

### `CameraQuantizer.discretize`

Converts continuous camera movement into discrete camera-token bins.

The default `MCDataset` parameters are:

- `camera_binsize = 9`;
- `camera_maxval = 90`;
- `camera_mu = 11.4887`;
- `quantization_scheme = "mu_law"`.

The default action vocabulary uses 21 bins for each camera axis.

### `MCDataset.make_action_vocab`

Constructs the action-token vocabulary.

The vocabulary includes:

- Minecraft action tokens;
- hotbar slots 1 through 9;
- camera axis 0 tokens;
- camera axis 1 tokens;
- `<act_bos>`;
- `<null_act>`;
- `<act_eos>`.

The vocabulary can be shifted by an `action_vocab_offset`.

The exact offset used by the 700M_16f model still needs to be traced through the pinned configuration and runtime code.

### `MCDataset.get_action_index_from_actiondict`

Constructs the official 11-token action sequence.

The token positions are:

- position 0: `<act_bos>`;
- position 1: camera axis 0;
- position 2: camera axis 1;
- position 3: hotbar;
- position 4: forward/back;
- position 5: left/right;
- position 6: sprint/sneak;
- position 7: use/attack;
- position 8: jump;
- position 9: drop/pickItem;
- position 10: `<act_eos>`.

Therefore, the official action length is 11 tokens.

### `MCDataset.read_jsonl`

Loads the recorded JSONL action records into an ordered list.

This establishes the source action format but does not by itself prove the exact causal relationship between a JSONL row and a model/video frame.

That alignment must be traced through the remaining pinned code and paired sample.

## Expected behavior

Raw Minecraft keyboard and mouse actions are normalized and encoded into an 11-token action sequence consisting of:

1. BOS;
2. camera axis 0;
3. camera axis 1;
4. hotbar;
5. forward/back;
6. left/right;
7. sprint/sneak;
8. use/attack;
9. jump;
10. drop/pick;
11. EOS.

## Adapter assumptions that must be tested

The MineOcclude adapter must verify that:

1. `action_length == 11`;
2. token 0 is BOS;
3. token 10 is EOS;
4. camera axis 0 appears before camera axis 1;
5. camera input ordering remains `[y/pitch, x/yaw]`;
6. camera scaling matches `360.0 / 2400.0`;
7. camera quantization matches the pinned MineWorld parameters;
8. conflicting action pairs follow MineWorld's official cancellation behavior;
9. hotbar encoding follows the official vocabulary;
10. the correct `action_vocab_offset` is used;
11. raw actions are converted through the official MineWorld logic rather than a separately invented encoding.

## Open questions

The remaining pinned files must resolve:

1. What exact `action_vocab_offset` is used by `700M_16f`?
2. Are the default camera parameters overridden by the configuration?
3. Where are the 11 action tokens combined with the visual tokens?
4. How exactly does one JSONL action align with one video/model frame?
5. Does an action describe the current frame or the transition to the next frame?
6. How are inventory and ESC records treated downstream?

## Review status

Reviewed and recorded for A0.4.

---
# 2. utils.py

## File

`utils.py`

## Microsoft revision

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## What this file controls

This file provides shared MineWorld utility functions used for:

- dynamically locating Python classes from configuration strings;
- instantiating model objects from configuration dictionaries;
- loading checkpoint state dictionaries into configured model classes;
- moving models to GPU;
- switching models into evaluation mode;
- casting the loaded model to float16;
- selecting the first valid directory or file path from several candidates;
- converting model tensors from the range `[-1, 1]` into uint8 image values.

For Person A, the most important behavior is the model construction and checkpoint-loading path.

## Relevant authoritative symbols

### `get_obj_from_str`

Takes a fully qualified Python target string, separates the module from the class name, imports the module, and returns the requested class or object.

This means MineWorld model classes are selected dynamically from configuration rather than being hard-coded directly into the loading utility.

### `instantiate_from_config`

Requires the configuration to contain a `target` field.

It instantiates the object named by:

`config["target"]`

using:

`config.get("params", dict())`

as keyword arguments.

Therefore, the pinned `700M_16f.yaml` configuration is authoritative for identifying the concrete model class and its constructor parameters.

### `load_model_from_config`

Instantiates the configured model and loads a provided state dictionary with:

`model.load_state_dict(sd, strict=False)`

The function explicitly raises an error if any model parameters are reported as missing.

Unexpected checkpoint keys are collected but are not explicitly rejected by this function.

When requested, the function also:

- moves the model to CUDA;
- switches the model into evaluation mode.

### `load_model`

This is the higher-level checkpoint-loading utility.

Checkpoint behavior depends on the filename:

- if the checkpoint ends in `.bin`, the object returned by `torch.load(ckpt)` is treated directly as the weight dictionary;
- otherwise, MineWorld loads the checkpoint on CPU and extracts the `"state_dict"` field.

The configured model is then created through `load_model_from_config`.

The state dictionary is subsequently loaded again with `strict=False`, and the resulting model is converted to `torch.float16`.

The exact runtime behavior must therefore preserve:

- the expected checkpoint container format;
- the configured model target;
- the configured model parameters;
- state-dictionary compatibility;
- evaluation mode;
- the expected floating-point dtype.

### `tensor_to_uint8`

Clamps tensors to the range `[-1, 1]`, remaps them to `[0, 1]`, moves them to CPU, multiplies by 255, and converts the result to NumPy `uint8`.

This provides evidence for one MineWorld output-image conversion path, but it does not by itself establish the authoritative model-input preprocessing path.

### `get_valid_dirs` and `get_valid_paths`

Return the first candidate directory or file path that actually exists.

These are path-resolution helpers and do not define scientific identity or model behavior.

## Expected behavior

MineWorld constructs its model dynamically from the YAML configuration.

The configuration must identify the model class using a `target` field and provide constructor parameters under `params`.

The checkpoint weights are then loaded into that configured model.

For ordinary non-`.bin` checkpoints, MineWorld expects the loaded checkpoint object to contain a top-level `"state_dict"` entry.

The loaded model is placed into evaluation mode when requested and is ultimately converted to float16 by `load_model`.

## Adapter assumptions that must be tested

The MineOcclude adapter must verify that:

1. the exact pinned `700M_16f.yaml` configuration is used;
2. the configured `target` resolves to the expected MineWorld model implementation;
3. the expected configuration parameters are passed unchanged unless an explicit, reviewed override exists;
4. the selected `700M_16f` checkpoint has the container structure expected by MineWorld;
5. the required `"state_dict"` exists for the checkpoint format being used;
6. model loading produces no missing required parameters;
7. the model is placed into evaluation mode for inference and activation extraction;
8. the runtime dtype matches the official loading path unless a deliberate validated change is recorded;
9. checkpoint loading is tied to exact file identity and hashes in MineOcclude rather than relying only on a filename.

## Important observations

`load_model_from_config` checks for missing keys and raises an error if any are present.

Unexpected keys are not explicitly rejected by that function.

`load_model` also calls `model.load_state_dict(weight, strict=False)` after `load_model_from_config` has already loaded the same supplied state dictionary.

The pinned upstream code therefore performs a second non-strict state-dictionary load in this path.

MineOcclude should not silently reinterpret this behavior. Any adapter implementation should either reuse the official loading path or explicitly test equivalence.

## Open questions

The remaining pinned files must resolve:

1. What exact `target` and constructor parameters are specified by `configs/700M_16f.yaml`?
2. What exact structure does the recovered `700M_16f.ckpt` use?
3. Which runtime entry point calls `load_model` for the 700M model?
4. Is float16 the complete runtime precision policy, or are later components/autocast contexts also involved?
5. What preprocessing function produces the model's input tensors before inference?
6. How is the shared VAE loaded, and does it use this same loading utility or another path?

## Review status

Reviewed and recorded for A0.4.

---

# 3. configs/700M_16f.yaml

## File

`configs/700M_16f.yaml`

## Microsoft revision

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## What this file controls

This is the authoritative configuration for constructing the MineWorld 700M 16-frame model.

It specifies:

- the top-level MineWorld model class;
- the underlying causal language-model class;
- the VAE configuration and checkpoint locations;
- the Transformer architecture;
- maximum sequence length;
- hidden dimension;
- layer count;
- attention-head configuration;
- vocabulary size;
- configured Transformer dtype.

## Relevant authoritative configuration

### Top-level model

`model.target` is:

`lvm.LlamaLVM`

Therefore, the authoritative top-level model object for this configuration is `lvm.LlamaLVM`.

The `model_class` parameter is:

`lvm.LlamaForCausalLM`

Therefore, the underlying causal language model used by this MineWorld configuration is `lvm.LlamaForCausalLM`.

### VAE configuration

The tokenizer/VAE target is:

`vae.VAE`

The expected VAE files are:

- `checkpoints/vae/config.json`
- `checkpoints/vae/vae.ckpt`

This confirms that the 700M model depends on the shared external VAE checkpoint and configuration.

The MineOcclude runtime must bind these files to exact identities and hashes rather than relying only on these relative filenames.

### Transformer configuration

The pinned configuration specifies:

- `max_position_embeddings = 5552`
- `hidden_size = 2048`
- `intermediate_size = 4096`
- `num_attention_heads = 32`
- `num_key_value_heads = 4`
- `num_hidden_layers = 20`
- `rope_theta = 10000.0`
- `torch_dtype = bfloat16`
- `rms_norm_eps = 1.0e-05`
- `vocab_size = 8262`
- `attention_bias = false`
- `mlp_bias = false`

## Token-length evidence

The configuration declares:

`max_position_embeddings = 5552`

The target model is the 16-frame configuration:

`700M_16f`

Dividing the maximum sequence length by the 16-frame context gives:

`5552 / 16 = 347`

This is consistent with a per-frame state/action sequence length of 347 tokens.

The pinned `mcdataset.py` review independently established that each action occupies exactly 11 tokens.

Therefore, the configuration strongly corroborates the project structure:

`336 visual tokens + 11 action tokens = 347 tokens`

and:

`347 tokens × 16 frames = 5552 positions`

The exact production of the 336 visual tokens still needs to be traced directly through the pinned VAE and model runtime code before being considered fully proven from source.

## Model architecture implications for Person A

The model configuration contains 20 Transformer layers.

Any Person A code that expects the complete set of model layers must test the actual loaded architecture against this pinned value instead of silently assuming it.

The configured hidden size is 2048.

Therefore, activation extraction from the relevant Transformer residual stream is expected to produce a hidden dimension associated with the 2048-dimensional model representation, subject to verification at the exact selected hook site.

The adapter must inspect the loaded real model and fail if the actual architecture disagrees with the pinned configuration.

## Dtype observation

The configuration declares:

`torch_dtype: bfloat16`

However, the pinned `utils.py` implementation later calls:

`model.to(torch.float16)`

inside `load_model`.

Therefore, the static configuration and the model-loading utility contain two different dtype signals.

The actual runtime dtype policy must be traced through the official inference entry points before MineOcclude freezes its runtime behavior.

MineOcclude must not silently choose one based only on this YAML file.

## Expected behavior

The 700M_16f checkpoint is expected to instantiate as a `lvm.LlamaLVM` using `lvm.LlamaForCausalLM` with the pinned Transformer parameters.

The model depends on the shared `vae.VAE` tokenizer and the VAE files located under `checkpoints/vae`.

The configured architecture has:

- 20 Transformer layers;
- hidden size 2048;
- maximum sequence length 5552;
- vocabulary size 8262.

The 5552-position context is consistent with 16 groups of 347 tokens.

## Adapter assumptions that must be tested

The MineOcclude adapter must verify that:

1. the loaded configuration is the pinned `700M_16f.yaml`;
2. the top-level model target is `lvm.LlamaLVM`;
3. the causal model class is `lvm.LlamaForCausalLM`;
4. the VAE target is `vae.VAE`;
5. the exact VAE config and checkpoint files are present and hash-bound;
6. the loaded model reports 20 Transformer layers;
7. the loaded model hidden size is 2048;
8. the maximum configured position count is 5552;
9. the actual tokenized 16-frame sequence agrees with the expected 5552-position layout;
10. the actual per-frame token structure agrees with the expected 347-token grouping;
11. the visual-token count is verified from real tokenizer/model behavior rather than inferred only from arithmetic;
12. the runtime dtype is verified from actual execution;
13. the loaded checkpoint architecture is compatible with all pinned configuration parameters;
14. the checkpoint and VAE assets are tied to exact file hashes and revisions.

## Resolved questions from earlier files

The configuration resolves:

- the top-level model target: `lvm.LlamaLVM`;
- the underlying causal model class: `lvm.LlamaForCausalLM`;
- the VAE target: `vae.VAE`;
- the expected VAE paths;
- the expected number of Transformer layers: 20;
- the expected hidden size: 2048;
- the maximum sequence length: 5552;
- the configured Transformer dtype: bfloat16.

The 5552-position sequence length strongly corroborates a 347-token grouping across 16 frames.

## Open questions

The remaining pinned files must resolve:

1. What exact `action_vocab_offset` is used?
2. How are the visual tokens produced, and where is the exact count of 336 established?
3. Where are the 336 visual tokens and 11 action tokens concatenated?
4. What is the exact causal frame/action ordering?
5. What actual dtype is used after the full runtime path executes?
6. Which exact module locations correspond to the 20 Transformer layers for activation hooking?
7. How does MineWorld load and invoke the shared VAE during preprocessing and decoding?
8. How does `vocab_size = 8262` divide between visual and action token vocabularies?

## Review status

Reviewed and recorded for A0.4.

---

# 4. mineworld.py

## File

`mineworld.py`

## Microsoft revision

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## What this file controls

This file is the official interactive MineWorld web-demo runtime.

For Person A, it provides authoritative evidence for:

- model and configuration loading;
- model input resolution;
- exact visual-token count;
- exact action-token count;
- action-vocabulary offset;
- video-frame preprocessing;
- VAE/tokenizer invocation;
- frame/action sequence construction;
- causal frame/action ordering;
- context-length calculation;
- Transformer cache prefilling;
- autoregressive image-token generation;
- runtime autocast behavior.

## Relevant authoritative constants

The pinned implementation declares:

`AGENT_RESOLUTION = (384, 224)`

`TOKEN_PER_IMAGE = 336`

`TOKEN_PER_ACTION = 11`

Therefore, the official interactive runtime directly establishes a per-frame state/action token group of:

`336 visual tokens + 11 action tokens = 347 tokens`

This is direct source evidence and no longer depends only on arithmetic inferred from the configuration.

## Context-length calculation

At startup, the runtime calculates:

`CONTEXT_LEN = max_position_embeddings / (TOKEN_PER_ACTION + TOKEN_PER_IMAGE)`

For the pinned `700M_16f.yaml` configuration:

`5552 / (11 + 336) = 16`

Therefore, the official runtime confirms:

- 336 visual tokens per image;
- 11 action tokens per action;
- 347 tokens per complete image/action group;
- 16-frame context length for the 700M_16f configuration.

## Action vocabulary offset

Both prerecorded actions and interactive actions are encoded with:

`action_vocab_offset = 8192`

The official calls are made through:

`MCDataset.get_action_index_from_actiondict(..., action_vocab_offset=8192)`

Therefore, for this pinned runtime, the action vocabulary begins at token ID offset 8192.

This resolves the open question from the `mcdataset.py` review.

The MineOcclude adapter must not infer or independently choose a different action-vocabulary offset.

## Vocabulary relationship

The pinned `700M_16f.yaml` configuration declares:

`vocab_size = 8262`

The runtime uses:

`action_vocab_offset = 8192`

This means the action vocabulary occupies the token-ID region beginning at 8192 within the model vocabulary.

The exact complete vocabulary cardinality should still be validated from the action-vocabulary construction itself and the loaded model rather than inferred only from these two numbers.

## Frame preprocessing

Inside `step_video`, each source video frame is:

1. read using OpenCV;
2. converted from BGR to RGB;
3. clipped to `[0, 255]`;
4. converted to `uint8`;
5. resized to `(384, 224)` using `cv2.INTER_LINEAR`;
6. converted into a Torch tensor;
7. rearranged from HWC to CHW;
8. converted to float;
9. divided by 255;
10. normalized with mean `[0.5, 0.5, 0.5]`;
11. normalized with standard deviation `[0.5, 0.5, 0.5]`.

The resulting normalized frames are passed to:

`tokenizer.tokenize_images(frames_tensor)`

This is the authoritative web-demo preprocessing path for converting source frames into the tensors presented to the VAE/tokenizer.

MineOcclude must reproduce or directly reuse this behavior unless another pinned official entry point establishes a different required preprocessing path for teacher-forced evaluation.

## Image tokenization

Image tensors are tokenized through:

`tokenizer.tokenize_images(frames_tensor)`

The tokenizer is obtained from:

`tokenizer = model.tokenizer`

The loaded model therefore owns the VAE/tokenizer used to convert normalized Minecraft frames into discrete image tokens.

After tokenization, the output is rearranged with:

`rearrange(images_token, '(b t) h w -> (b t) (h w)', b=1)`

The runtime expects each flattened image-token sequence to contain exactly 336 image tokens, as established by `TOKEN_PER_IMAGE`.

## Frame/action causal sequence construction

When reference frames are loaded, the runtime reads:

- video frame `i`;
- JSONL action record `i`.

Each frame and action are independently converted into image tokens and 11 action tokens.

Before constructing the Transformer context, the final action is removed.

The runtime then builds the sequence by concatenating each non-final image with its same-index action:

`frame_0 + action_0`

`frame_1 + action_1`

`frame_2 + action_2`

and so on.

The final reference frame is appended without a following action.

Conceptually, the sequence has the form:

`[frame_0, action_0, frame_1, action_1, ..., frame_N]`

This establishes the official causal ordering used by the interactive runtime.

Action record `i` follows frame `i` in token order and conditions the subsequent image generation.

MineOcclude must preserve this ordering.

It must not:

- shift actions backward;
- shift actions forward;
- use nearest-time matching;
- pair rows by filename or row order without explicit identity validation.

## JSONL/video alignment

Inside `step_video`, the runtime uses the same integer index `i` to select:

`json_data[i]`

and:

video frame `i`

Therefore, within the official paired demo input, JSONL row `i` is directly associated with video frame index `i` before sequence construction.

After tokenization, the sequence uses:

`frame_i + action_i`

followed eventually by the next frame.

This provides the strongest pinned evidence so far for the causal interpretation that action `i` is the action following state/frame `i` and conditioning the next generated state.

MineOcclude must still validate this convention against the actual paired `scene.jsonl` and `scene.mp4` sample and against the local-inference path before freezing the final adapter behavior.

## Transformer runtime path

The loaded top-level model exposes:

`model.transformer`

The interactive runtime directly invokes Transformer methods including:

- `model.transformer.refresh_kvcache()`;
- `model.transformer.prefill_for_gradio(...)`;
- `model.transformer.decode_img_token_for_gradio(...)`;
- `model.transformer.diagd_img_token_for_gradio(...)`.

Therefore, `model.transformer` is the authoritative Transformer runtime object used for interactive generation.

The exact internal module path corresponding to each of the 20 configured Transformer layers still needs to be established from the model implementation or real runtime introspection before activation hooks are attached.

## Initial context construction

The initial reference context is assembled by pairing all non-final reference frames with their corresponding actions and appending the final frame without an action.

The combined sequence is passed to:

`model.transformer.prefill_for_gradio(_vis_act)`

This initializes the Transformer key/value cache and returns the position used for continued generation.

## Interactive generation

For a new user action, the runtime:

1. constructs the normalized action dictionary;
2. places camera values in `[y, x]` order;
3. encodes the action using `action_vocab_offset=8192`;
4. converts the 11 action IDs to a CUDA tensor;
5. passes the action tokens to the Transformer;
6. generates the next image tokens;
7. decodes the generated image tokens using `tokenizer.token2image`.

For ordinary autoregressive generation, the runtime calls:

`decode_img_token_for_gradio`

with:

`max_new_tokens = TOKEN_PER_IMAGE + 1`

The source comment states that the additional token is used to fill the KV cache.

For diagonal decoding, the runtime calls:

`diagd_img_token_for_gradio`

with:

`max_new_tokens = TOKEN_PER_IMAGE`.

MineOcclude must distinguish the actual 336 visual-token frame representation from any additional generation/cache-control token used internally by the runtime.

## Runtime dtype behavior

The source-frame tokenization path executes under:

`torch.autocast(device_type='cuda', dtype=torch.float16)`

Interactive generation also executes under CUDA float16 autocast.

The earlier configuration declares:

`torch_dtype = bfloat16`

while `utils.load_model` converts the model to:

`torch.float16`.

The interactive runtime therefore provides additional evidence that the executed web-demo path operates under float16 model conversion and float16 autocast despite the static Transformer configuration containing a bfloat16 dtype field.

The final MineOcclude runtime policy should still be checked against `inference.py`, since the research project is closer to the local inference/teacher-forced path than the Gradio interface.

## Default runtime paths

The argument parser declares defaults including:

- scene: `./assets/scene.mp4`;
- model checkpoint: `./checkpoints/700M_16f.pt`;
- configuration: `./configs/700M_16f.yaml`;
- reference frames: 8.

The official README and recovered asset mirror may use different checkpoint filename extensions or locations.

MineOcclude must resolve the actual recovered checkpoint filename by inspecting the real ModelScope asset rather than assuming the default `.pt` path or renaming an asset without verification.

## Expected behavior

For the official interactive MineWorld runtime:

- source images are resized to 384×224;
- images are normalized from `[0, 1]` to approximately `[-1, 1]`;
- the model tokenizer produces 336 image tokens per frame;
- every action is encoded into 11 tokens;
- action token IDs use an offset of 8192;
- one complete frame/action group occupies 347 tokens;
- the 700M_16f configuration supports 16 such 347-token positions within 5552 maximum positions;
- reference context follows the causal pattern `[frame_i, action_i, ..., final_frame]`;
- generation proceeds by supplying an action and generating the next image-token sequence.

## Adapter assumptions that must be tested

The MineOcclude adapter must verify that:

1. source frames entering the official preprocessing path have the expected source identity;
2. preprocessing resizes frames to exactly 384×224;
3. interpolation matches the pinned runtime when equivalent preprocessing is required;
4. color ordering is RGB before tensor conversion;
5. pixel scaling and normalization match the pinned runtime;
6. `tokenizer.tokenize_images` returns exactly 336 flattened image tokens per frame;
7. each action produces exactly 11 action tokens;
8. action token IDs use offset 8192;
9. every complete image/action group occupies 347 tokens;
10. the 700M_16f context length resolves to 16 groups;
11. frame/action ordering is `[frame_i, action_i]`;
12. the final context frame has no following action until a new action is supplied;
13. JSONL row and source video frame identities are aligned exactly;
14. no manual index shifting or nearest-time matching is introduced;
15. the runtime Transformer object is the expected `model.transformer`;
16. the loaded real model exposes the expected 20-layer architecture;
17. actual hook sites are discovered and validated against the loaded real model before extraction;
18. runtime dtype/device behavior is recorded rather than inferred only from static configuration;
19. generated-image token count remains distinct from any extra KV-cache/control token;
20. exact checkpoint and VAE identities are hash-bound.

## Resolved questions from earlier files

The pinned `mineworld.py` resolves:

- action vocabulary offset: 8192;
- visual tokens per image: 336;
- action tokens per action: 11;
- total per-frame image/action group: 347;
- 700M_16f context length: 16;
- model input resolution: 384×224;
- official web-demo image preprocessing path;
- frame/action token ordering;
- same-index JSONL/video pairing within the demo path;
- the top-level Transformer runtime object: `model.transformer`;
- the VAE/tokenizer access path: `model.tokenizer`;
- interactive generation under CUDA float16 autocast.

## Open questions

The remaining pinned files must resolve or verify:

1. Does `inference.py` use the same preprocessing path?
2. Does `inference.py` use the same action-vocabulary offset of 8192?
3. Does local inference preserve the same `[frame_i, action_i]` causal ordering?
4. What exact model-layer module path should activation hooks target?
5. What is the runtime dtype behavior in the local inference path?
6. What exact checkpoint filename and container structure are present in the recovered ModelScope assets?
7. Does the paired `scene.jsonl`/`scene.mp4` sample empirically satisfy the expected row/frame correspondence?
8. Are there any differences between interactive generation and the teacher-forced path needed by MineOcclude?

## Review status

Reviewed and recorded for A0.4.

---

# 5. inference.py

## File

`inference.py`

## Microsoft revision

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## What this file controls

This file is the official local MineWorld inference and validation-generation entry point.

For Person A, it provides authoritative evidence for:

- local model loading;
- validation video and action loading;
- action-token encoding;
- action-vocabulary offset;
- local frame preprocessing;
- VAE/tokenizer invocation;
- generation inputs;
- generated visual-token count;
- runtime precision behavior;
- naive versus diagonal generation.

## Relevant authoritative constants

The pinned implementation declares:

`TOKEN_PER_PIX = 336`

and:

`TOKEN_PER_IMAGE = 347`

with the comment:

`IMAGE = PIX + ACTION`

The actual generation calls use:

`TOKEN_PER_PIX * args.frames`

as the number of image tokens to generate.

Therefore, the local inference path directly confirms that each generated visual frame consists of 336 visual tokens.

The value 347 is consistent with:

`336 visual tokens + 11 action tokens = 347`

as established independently by `mcdataset.py` and `mineworld.py`.

## Action vocabulary offset

Every action loaded by the local inference path is encoded using:

`MCDataset.get_action_index_from_actiondict(..., action_vocab_offset=8192)`

Therefore, local inference independently confirms the same action-vocabulary offset used by the interactive runtime:

`8192`

This is now supported by both official entry points.

## Action loading

The local inference path reads the paired JSONL file line by line.

For each action record it:

1. parses the action dictionary;
2. converts the `camera` field to a NumPy array;
3. passes the dictionary directly to:
   `MCDataset.get_action_index_from_actiondict`;
4. uses `action_vocab_offset=8192`;
5. stores the resulting 11-token action sequence.

Unlike the interactive `mineworld.py` path, this local-inference path appears to expect action records that have already been normalized into the MineWorld action-dictionary format.

It does not call:

`json_action_to_env_action`

before tokenization.

Therefore, MineOcclude must distinguish between:

- raw keyboard/mouse JSON records requiring official normalization;
- already-normalized MineWorld action dictionaries.

The adapter must validate which format it receives rather than silently assuming one.

## Local frame preprocessing

The local inference path reads source video frames using OpenCV.

For each initial frame it:

1. reads frame index `frame_idx`;
2. converts BGR to RGB;
3. clips values to `[0, 255]`;
4. converts to `uint8`;
5. converts the frame to a Torch tensor;
6. rearranges HWC to CHW;
7. converts to float;
8. divides by 255;
9. normalizes using mean `[0.5, 0.5, 0.5]`;
10. normalizes using standard deviation `[0.5, 0.5, 0.5]`.

The frames are then passed to:

`model.tokenizer.tokenize_images(frames)`

## Important preprocessing difference from mineworld.py

The interactive `mineworld.py` path explicitly resizes source frames to:

`384 × 224`

using:

`cv2.INTER_LINEAR`

before tokenization.

The local `inference.py` path does not explicitly resize frames.

Therefore, this file alone does not prove that arbitrary source-resolution frames are accepted by local inference.

The likely requirement is that the validation videos already have the required model input resolution, but this must be verified from the actual paired validation sample or another authoritative source.

MineOcclude must not silently omit resizing merely because this particular entry point does not perform it.

The adapter must define and validate exactly where the required 384×224 preprocessing occurs.

## Image tokenization

The initial frames are tokenized using:

`model.tokenizer.tokenize_images(frames)`

The tokenized frames are rearranged into flattened per-frame visual-token sequences.

The generated output length is always based on:

`336 × number_of_generated_frames`

Therefore, local inference independently verifies the 336-token visual-frame representation.

## Local generation path

The initial visual frame tokens are flattened into:

`image_input`

Actions for future generation are collected separately into:

`action_all`

The Transformer is then called using either:

`model.transformer.naive_generate(...)`

or:

`model.transformer.img_diagd_generate(...)`

Both receive:

- the initial image-token input;
- the future action-token sequences;
- a request to generate exactly 336 visual tokens per requested output frame.

Therefore, unlike the Gradio prefill path, the local inference entry point does not manually construct one single visible tensor containing explicit:

`[frame, action, frame, action]`

groups.

Instead, it supplies initial image tokens and future action tokens separately to the Transformer generation method.

The internal Transformer generation implementation is therefore responsible for combining or scheduling the action tokens correctly during generation.

MineOcclude must not assume that the top-level `inference.py` tensor layout alone completely specifies the internal action/image sequence.

## Frame/action indexing observation

The initial source frames are loaded from:

`0` through `demo_num - 1`

The future action slice begins at:

`action_list[demo_num]`

through the requested generation range.

For example, with:

`demo_num = 1`

the initial source frame is frame 0, while the first supplied future action is action-list index 1.

This indexing does not obviously match the same-index frame/action construction visible in `mineworld.py`.

The reason cannot be determined from `inference.py` alone.

Therefore, MineOcclude must not freeze a final causal frame/action alignment based only on one entry point.

The discrepancy must be resolved using:

- the actual paired JSONL/MP4 sample;
- the internal Transformer generation implementation if necessary;
- a runtime alignment test.

No manual index shift should be introduced without explicit evidence.

## Runtime precision

At module startup, the implementation sets:

`torch.backends.cuda.matmul.allow_tf32 = False`

Therefore, TensorFloat-32 matrix multiplication is explicitly disabled in this inference entry point.

Both image tokenization and model generation execute under:

`torch.autocast(device_type="cuda", dtype=torch.float16)`

The shared `load_model` utility also converts the loaded model to float16.

Therefore, the official local inference path provides strong evidence that runtime inference executes using float16 behavior despite the static YAML configuration containing:

`torch_dtype = bfloat16`

The MineOcclude runtime must record the actual loaded parameter dtype and execution autocast policy directly.

## Model runtime object

Like `mineworld.py`, local inference operates through:

`model.transformer`

and:

`model.tokenizer`

The generation methods used are:

- `model.transformer.naive_generate`;
- `model.transformer.img_diagd_generate`.

This independently confirms that the top-level MineWorld object exposes:

- the Transformer through `model.transformer`;
- the VAE/tokenizer through `model.tokenizer`.

The exact internal layer modules for activation hooks still require direct model-code inspection or runtime introspection.

## Generated output

The generated token stream is split into chunks of exactly 336 tokens.

Each 336-token chunk is decoded using:

`tokenizer.token2image`

and written as one video frame.

Therefore, the visual generation boundary is exactly 336 tokens per output frame in this official inference path.

## Expected behavior

The official local inference path:

- loads the configured MineWorld model;
- reads paired MP4 and JSONL files;
- encodes normalized action dictionaries using offset 8192;
- normalizes initial RGB frames;
- tokenizes them through `model.tokenizer`;
- represents each visual frame with 336 tokens;
- supplies future actions separately to the Transformer generation method;
- generates exactly 336 visual tokens per requested future frame;
- executes tokenization and generation under CUDA float16 autocast;
- disables TF32 matrix multiplication.

## Adapter assumptions that must be tested

The MineOcclude adapter must verify that:

1. input action records are classified correctly as raw or already normalized;
2. normalized actions use the official MineWorld action encoder;
3. action token IDs use offset 8192;
4. every encoded action contains exactly 11 tokens;
5. every tokenized visual frame contains exactly 336 tokens;
6. every generated visual frame contains exactly 336 tokens;
7. source-frame color ordering is RGB before tokenization;
8. pixel scaling and normalization match the official path;
9. the required 384×224 resolution is enforced at the correct preprocessing boundary;
10. no accidental double resizing occurs;
11. model generation uses the expected Transformer object;
12. actual model/runtime dtype is recorded;
13. TF32 policy is recorded where reproducibility requires it;
14. causal action/frame indexing is verified before scientific extraction;
15. no manual index shifting is introduced without evidence;
16. the exact real checkpoint and VAE assets are hash-bound.

## Resolved questions from earlier files

The local inference path independently confirms:

- action vocabulary offset: 8192;
- visual tokens per frame: 336;
- normalized frame input range;
- tokenizer access through `model.tokenizer`;
- Transformer access through `model.transformer`;
- float16 autocast during tokenization;
- float16 autocast during generation;
- generated visual frames containing exactly 336 tokens;
- action sequences supplied separately to local Transformer generation methods.

## Open questions

The remaining paired-sample review and runtime inspection must resolve:

1. What exact resolution is stored in the official paired MP4 sample?
2. What exact schema is stored in the paired JSONL sample?
3. How many JSONL rows exist relative to video frames?
4. What exact semantic transition does JSONL row `i` represent?
5. Why does local inference begin future actions at `action_list[demo_num]`?
6. How does the internal generation implementation schedule the supplied actions relative to generated frames?
7. What exact loaded module path corresponds to each of the 20 Transformer layers?
8. What exact checkpoint filename and container structure exist in the recovered ModelScope assets?

## Review status

Reviewed and recorded for A0.4.

---

# 6. Paired scene.jsonl / scene.mp4 sample

## Asset source

Recovered MineWorld model/sample asset repository:

`AI-ModelScope/mineworld`

Downloaded from the ModelScope repository path:

`gradio_scene/scene.jsonl`

`gradio_scene/scene.mp4`

The files were downloaded separately from the Microsoft source-code repository.

The Microsoft source revision used for interpreting these files is:

`9f49efbcc68a5f0cf60e78f0abc566eac409282f`

## Exact file identities

### scene.mp4

SHA-256:

`B546E7657505004223742E2174E01D0B6A19091DE7EE39A2F213BCF003C243DE`

Observed file size:

`124782221 bytes`

### scene.jsonl

SHA-256:

`0029DAF06496BB974305431A20E8C9D419791F362098BF9D57EE8B8E0F036F9B`

Observed file size:

`15326380 bytes`

These hashes identify the exact paired sample files reviewed for A0.4.

## Observed video properties

The recovered `scene.mp4` contains:

- frame count: 4152;
- frame rate: 20.0 FPS;
- width: 640 pixels;
- height: 360 pixels.

Therefore, the recovered paired sample provides direct evidence for the source capture format:

`640 × 360 at 20 FPS`

The official interactive MineWorld runtime subsequently resizes these source frames to:

`384 × 224`

before VAE tokenization.

This supports the MineOcclude preprocessing boundary:

`640 × 360 captured source frame`

followed by:

`384 × 224 MineWorld model input frame`

for the pinned interactive path.

## JSONL cardinality

The recovered `scene.jsonl` contains:

`4152 rows`

The recovered `scene.mp4` contains:

`4152 frames`

Therefore:

`JSONL row count == MP4 frame count == 4152`

This establishes exact one-to-one cardinality for the recovered paired sample.

## JSONL source schema

The first observed JSONL record contains raw capture information including:

- `mouse`;
- `keyboard`;
- `isGuiOpen`;
- `isGuiInventory`;
- `hotbar`;
- `yaw`;
- `pitch`;
- `xpos`;
- `ypos`;
- `zpos`;
- `tick`;
- `milli`;
- `inventory`;
- `serverTick`;
- `serverTickDurationMs`;
- `stats`.

The `mouse` object contains fields including:

- `x`;
- `y`;
- `dx`;
- `dy`;
- `scaledX`;
- `scaledY`;
- `dwheel`;
- `buttons`;
- `newButtons`.

The `keyboard` object contains fields including:

- `keys`;
- `newKeys`;
- `chars`.

Therefore, this paired Gradio sample uses the raw keyboard/mouse capture schema expected by:

`MCDataset.json_action_to_env_action`

rather than the already-normalized action-dictionary format consumed directly by the local `inference.py` validation path.

MineOcclude must explicitly identify which input action format it receives before action tokenization.

## Frame/JSONL pairing evidence

The paired sample has exactly:

`4152 video frames`

and:

`4152 JSONL records`.

The pinned `mineworld.py` implementation uses the same integer index `i` to retrieve:

`json_data[i]`

and video frame:

`i`.

It then converts the same-index raw action record through:

`MCDataset.json_action_to_env_action`

and:

`MCDataset.get_action_index_from_actiondict`.

Therefore, the recovered sample and pinned interactive runtime jointly support exact same-index pairing between source video frame `i` and JSONL record `i`.

The token sequence subsequently places:

`frame_i`

before:

`action_i`

in the Transformer context.

This is consistent with action `i` being the action associated with the transition following state/frame `i`.

A later runtime alignment test should still verify the final scientific causal convention before MineOcclude processes real experimental data.

No manual row shift, nearest-time match, or filename-based reconstruction is permitted.

## Tick and timing evidence

The paired JSONL records contain timing and synchronization fields including:

- `tick`;
- `milli`;
- `serverTick`;
- `serverTickDurationMs`.

This confirms that the original MineWorld data format retains timing metadata in addition to simple row order.

MineOcclude's own trajectory identity and synchronization system should continue to preserve explicit timing and identity fields rather than reducing alignment to array position alone.

## Relationship to MineOcclude capture requirements

The recovered official sample directly supports the expected source characteristics:

- source resolution: 640 × 360;
- frame rate: 20 FPS;
- paired frame/action record cardinality.

The pinned MineWorld interactive runtime establishes the subsequent preprocessing to:

- model resolution: 384 × 224.

The pinned action code establishes:

- 11 action tokens per action;
- action-vocabulary offset 8192.

The pinned model/runtime code establishes:

- 336 visual tokens per frame;
- 347 total visual/action tokens per complete group;
- 16-frame context for `700M_16f`.

## Adapter assumptions that must be tested

The MineOcclude adapter and data handoff must verify that:

1. source frames are captured at the expected 640 × 360 resolution;
2. the expected runtime cadence is 20 Hz;
3. source video-frame cardinality exactly matches the corresponding action/state record cardinality;
4. every frame and action record is joined by explicit scientific identity;
5. source ordering agrees with the pinned same-index sample convention;
6. raw keyboard/mouse records are passed through the official normalization logic before action tokenization;
7. already-normalized action dictionaries are not normalized a second time;
8. source frames are converted to 384 × 224 at the authoritative preprocessing boundary;
9. exact file and artifact hashes are recorded;
10. no nearest-time or manual index repair is used to hide alignment failures.

## Resolved questions from earlier files

The paired sample resolves:

- official recovered sample resolution: 640 × 360;
- recovered sample frame rate: 20 FPS;
- paired sample video-frame count: 4152;
- paired sample JSONL-record count: 4152;
- one-to-one sample cardinality;
- the Gradio sample action format is raw keyboard/mouse capture data;
- the paired sample contains explicit tick and timing metadata.

Combined with the pinned source review, A0.4 now has traceable evidence for:

- 640 × 360 source capture;
- 20 FPS source cadence;
- 384 × 224 MineWorld preprocessing;
- 336 visual tokens;
- 11 action tokens;
- 347 tokens per visual/action group;
- 16-frame `700M_16f` context;
- action-vocabulary offset 8192;
- same-index paired-sample frame/JSONL access;
- the model, Transformer, and tokenizer ownership paths.

## Remaining runtime questions

The following do not block completion of this code-reading sign-off but must be verified during later runtime phases:

1. the exact semantic causal alignment of real MineOcclude capture rows under live execution;
2. the exact loaded Transformer layer module paths used for hooks;
3. the actual loaded checkpoint container structure;
4. actual model and activation dtypes during execution;
5. real checkpoint compatibility with the pinned configuration;
6. exact checkpoint and VAE SHA-256 identities once the required runtime assets are downloaded.

## Review status

Reviewed and recorded for A0.4.

---
