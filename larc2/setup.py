from setuptools import setup, find_packages

setup(
    name="larc2",
    version="0.1.0",
    packages=find_packages(),
    package_dir={"": "."},
    install_requires=[
        "websockets",
        "python-rtmidi",
        "pytest",
        "pytest-asyncio",
        "pytest-timeout",
        "psutil"  # Added for system diagnostics
    ],
    python_requires=">=3.8",
    package_data={"": ["*.json", "*.yaml"]},
    include_package_data=True
)
