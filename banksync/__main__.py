"""Allow running banksync as `python -m banksync <command> ...`."""

from .banksync import main

raise SystemExit(main())
