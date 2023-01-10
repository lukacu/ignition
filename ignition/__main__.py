import sys, time
import signal

from ignition.program import ProgramGroup

class shutdown_handler:
    
    def __init__(self):
        self.triggered = False
    
    def __call__(self, signum, frame):
        self.triggered = True

def main():
    if len(sys.argv) > 1:
        try:
            group = ProgramGroup.read(sys.argv[1])
        except ValueError as e:
            print("Error opening launch file %s: %s" % (sys.argv[1], e))
            sys.exit(1)

        stop = shutdown_handler()

        signal.signal(signal.SIGTERM, stop)

        try:
            group.announce("Starting up ...")
            group.start()

            time.sleep(1)
            
            while group.valid() and not stop.triggered:
                time.sleep(0.5)

        except KeyboardInterrupt:
            pass

        group.announce("Shutting down ...")
        
        try:
            group.stop()
        except KeyboardInterrupt:
            group.stop(True)

        sys.exit(0)
    else:
        print("Missing launch file")
        sys.exit(1)

if __name__ == '__main__':
    main()
