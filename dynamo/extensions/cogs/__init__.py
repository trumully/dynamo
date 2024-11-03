from pkgutil import ModuleInfo, iter_modules

EXTENSIONS: set[ModuleInfo] = set(iter_modules(__path__, f"{__package__}."))

__all__ = ("EXTENSIONS",)
