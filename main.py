"""
main.py
CLI entry point for the multi-agent travel planner.

Usage:
    python main.py "Plan a 3-day trip to Kyoto, June 10-12, I like temples and food"
"""

import sys

from orchestrator import plan_trip


def main():
    if len(sys.argv) < 2:
        print('Usage: python main.py "Plan a 3-day trip to Kyoto, June 10-12, I like temples and food"')
        sys.exit(1)

    request = " ".join(sys.argv[1:])
    itinerary = plan_trip(request)
    print("\n" + itinerary + "\n")


if __name__ == "__main__":
    main()
