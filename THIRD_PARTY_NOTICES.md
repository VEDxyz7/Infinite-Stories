# Source, assets and third-party obligations

Project-authored source, the Last Light fictional chapter, and procedural pixel
textures in `OriginalArt.cs` are provided under the repository MIT license.
Selected Kenney RPG Urban Pack PNG sprites and Interface Sounds OGG clips are
included under CC0; original pack licences are retained under
`client/Assets/ThirdParty/Kenney/`. Source: https://kenney.nl/assets/rpg-urban-pack
and https://kenney.nl/assets/interface-sounds . Attribution is optional; the game
credits Kenney. No proprietary reference-game art or cultural response data is bundled. No artist collaboration or personality inference is asserted.

Unity Editor, Unity runtime, engine modules, LegacyRuntime font, uGUI and test
packages remain subject to their Unity/package licenses. Unity Editor activation
and the terms applicable to the user are separate from this source license.

Backend distributions are installed from the pinned Python requirements and
retain their individual license metadata in the environment/image. Qloo tooling
is an isolated npm dependency under `tools/qloo`; the package and its transitive
notices remain theirs. No node_modules or proprietary Qloo results are included
in this source repository. A dependency inventory and license review must be
rechecked against actual release artifacts before publication.

MIT licensing of this project does not authorize redistribution of Qloo API
data, third-party marks, cultural images, or provider output. Those rights
remain a separate blocked release check.

## Optional local inference runtime and weights

The optional native Ollama runtime is downloaded separately into ignored local
storage; it is not bundled in this source or WebGL build. Ollama is MIT licensed:
https://github.com/ollama/ollama/blob/main/LICENSE
Qwen3 4B/8B weights used for local evaluation are Apache-2.0 licensed:
https://huggingface.co/Qwen/Qwen3-4B and https://huggingface.co/Qwen/Qwen3-8B
Preserve the applicable license/notice files if distributing runtime or weights.
Model-card capabilities do not replace game-specific acceptance evaluation.

Qwen3.5 4B (local MLX/NVFP4 evaluation) is Apache-2.0 licensed:
https://ollama.com/library/qwen3.5:4b
