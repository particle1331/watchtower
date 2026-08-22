"""Discover Jupyter kernels that can be passed to ``wt run --kernel``."""

from jupyter_client.kernelspec import KernelSpecManager


def available_kernel_names() -> list[str]:
    """Return installed Jupyter kernel names in stable display order."""
    return sorted(KernelSpecManager().find_kernel_specs())


def available_kernel_rows() -> list[tuple[str, str, str]]:
    """Return ``(name, language, display_name)`` rows for installed kernels."""
    manager = KernelSpecManager()
    rows = []
    for name in sorted(manager.find_kernel_specs()):
        spec = manager.get_kernel_spec(name)
        rows.append((name, spec.language or "", spec.display_name or name))
    return rows
