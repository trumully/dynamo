from pkgutil import ModuleInfo, iter_modules

EXTENSIONS: set[ModuleInfo] = {
    module for module in iter_modules(__path__, f"{__package__}.") if not module.name.split(".")[-1].startswith("_")
}


__all__ = ("EXTENSIONS",)
