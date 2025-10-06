from setuptools import setup, find_packages

setup(
    name="codex_sorter",          # Name of your package
    version="0.1.1",                   # Version number (semantic: MAJOR.MINOR.PATCH)
    packages=find_packages(),          # Automatically discover sub-packages
    description="OCR stack to classify trading cards and operate a 3d printer to sort them",  # One-line description
    long_description=open("README.md").read(),  # Optional: full README content
    long_description_content_type="text/markdown",  # If using markdown
    author="PraxisOG",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/yourproject",  # Project homepage (optional)
    license="MIT",                     # License type (e.g., MIT, Apache-2.0)
    
    install_requires=[               # Runtime dependencies
        "requests>=2.25.1",
        "numpy>=1.21.2"
    ],
    
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Match your license
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha"          # Optional: project maturity
    ],
    
    python_requires='>=3.6',         # Minimum Python version required
    
    # Optional extras for optional features
    extras_require={
        'dev': ['pytest', 'black'],
        'docs': ['sphinx']
    },
)
