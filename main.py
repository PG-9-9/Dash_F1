import logging
import sys

if __name__ == "__main__":

  if "--verbose" not in sys.argv:# fastf1 logging is disabled by default
    logging.getLogger("fastf1").setLevel(logging.CRITICAL)

  from src.server.app import main as server_main

  server_args = [arg for arg in sys.argv[1:] if arg not in ("--server", "--verbose")]
  if "--sprint" in server_args:
    server_args.remove("--sprint")
    server_args.extend(["--session", "S"])
  sys.exit(server_main(server_args))
