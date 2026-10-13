"""Bridge pack: expose comfyui-gguf-loader's GGUF loaders under unique names.

WHY THIS EXISTS
---------------
Two installed packs register the *same* node names (``UnetLoaderGGUF``,
``UnetLoaderGGUFAdvanced``):

  * ``ComfyUI-GGUF``        — upstream city96 pack; its ``detect_arch`` has NO
                              MiniMax-H3 entry, so H3 GGUFs fail with
                              "This model is not currently supported -
                               (Unknown model architecture!)".
  * ``comfyui-gguf-loader`` — newer fork that DOES support H3: its
                              ``tools/convert.py`` has ``ModelLTX2`` (detects H3
                              from the tensor signature) and ``loader.py`` maps
                              that to arch ``minimax_h3`` (in ``IMG_ARCH_LIST``).

In this environment ``ComfyUI-GGUF`` wins the name collision, so
``UnetLoaderGGUF`` resolves to the pack that cannot load H3.

This bridge re-registers ``comfyui-gguf-loader``'s classes under distinct names
(``UnetLoaderGGUF_H3`` / ``UnetLoaderGGUFAdvanced_H3``) so H3 GGUFs are
loadable **without touching any existing pack**.

ADDITIVE ONLY: this pack adds new node names; it modifies nothing. Delete this
directory to remove the bridge.

ORDER-INDEPENDENT: the real pack is resolved lazily at INPUT_TYPES / call time
(by then every custom node pack has been imported), so this bridge does not
depend on custom-node load order.
"""

from __future__ import annotations

import os
import sys

_PACK_DIRNAME = "comfyui-gguf-loader"
_LOADER_NAMES = ("UnetLoaderGGUF", "UnetLoaderGGUFAdvanced")
_SUFFIX = "_H3"


def _find_pack():
    """Return the already-imported ``comfyui-gguf-loader`` module, or None."""
    marker = os.sep + _PACK_DIRNAME + os.sep
    for mod in list(sys.modules.values()):
        try:
            path = getattr(mod, "__file__", None) or ""
        except Exception:
            continue
        if marker in path and hasattr(mod, "NODE_CLASS_MAPPINGS"):
            return mod
    return None


def _make_proxy(real_name: str):
    class _Proxy:
        RETURN_TYPES = ("MODEL",)
        RETURN_NAMES = ("model",)
        FUNCTION = "load_unet"
        CATEGORY = "CCTech/GGUF (H3 bridge)"
        DESCRIPTION = (
            "Bridge to comfyui-gguf-loader's loader (supports MiniMax-H3 GGUFs). "
            "Use when UnetLoaderGGUF reports 'Unknown model architecture!'."
        )

        @classmethod
        def INPUT_TYPES(cls):
            pack = _find_pack()
            if pack is None or real_name not in pack.NODE_CLASS_MAPPINGS:
                raise RuntimeError(
                    f"[h3-gguf-bridge] cannot resolve '{real_name}' from "
                    f"{_PACK_DIRNAME}; is that pack installed and loaded?"
                )
            return pack.NODE_CLASS_MAPPINGS[real_name].INPUT_TYPES()

        def load_unet(self, *args, **kwargs):
            pack = _find_pack()
            if pack is None or real_name not in pack.NODE_CLASS_MAPPINGS:
                raise RuntimeError(
                    f"[h3-gguf-bridge] cannot resolve '{real_name}' from "
                    f"{_PACK_DIRNAME}"
                )
            return pack.NODE_CLASS_MAPPINGS[real_name]().load_unet(*args, **kwargs)

    _Proxy.__name__ = real_name + _SUFFIX
    _Proxy.__qualname__ = _Proxy.__name__
    return _Proxy


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

for _name in _LOADER_NAMES:
    _node = _name + _SUFFIX
    NODE_CLASS_MAPPINGS[_node] = _make_proxy(_name)
    NODE_DISPLAY_NAME_MAPPINGS[_node] = f"UNET Loader (GGUF, H3 bridge) [{_name}]"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Note: the real pack may not be imported yet at this point; that is fine,
# _find_pack() runs lazily later. Report early only as a diagnostic.
if _find_pack() is None:
    print(
        f"[h3-gguf-bridge] note: '{_PACK_DIRNAME}' not in sys.modules yet; "
        "will resolve lazily at node use time."
    )
