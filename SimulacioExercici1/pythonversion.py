import simpy
import random
import math

# --- Setup: Global Parameters and Functions ---

# AGPSS function RN1,R (R is likely a variable/result, RN1 is the function name)
# The values 1->1, 2->2, ..., 100->6400 suggest a pattern, but it's not a standard
# random number distribution. For simplicity and following the AGPSS text,
# we'll implement the specified steps and use standard distributions for the
# time advances where indicated.

# FACILITIES/RESOURCES
MAC_CAPACITY = 6
CAM_CAPACITY = 12

# ADVANCE time parameters
ADVANCE_SERVICE_MEAN = 0.75
ADVANCE_SERVICE_ERR_MEAN = 15
ADVANCE_SERVICE_ERR_DEV = 2
ADVANCE_CAM_MEAN = 372.5
ADVANCE_CAM_DEV = 2.5


# A helper function to simulate the AGPSS 'FN$XPDIS' (Exponential Distribution)
# SimPy's env.timeout expects a time value.
def xpon_dist(mean):
    """Returns a time value from an Exponential Distribution."""
    # SimPy often uses standard Python/random module functions
    return random.expovariate(1.0 / mean)

# A helper function for 'ADVANCE X,Y' (Uniform/Normal/Triangular depending on system)
# Given the AGPSS usage, 'ADVANCE X,Y' often means a uniform distribution [X-Y, X+Y]
# or a normal distribution with mean X and standard deviation Y.
# We'll use a Normal Distribution as it's common in this context.
def normal_dist(mean, stdev):
    """Returns a time value from a Normal Distribution."""
    # Ensure time is non-negative
    return max(0, random.gauss(mean, stdev))

# --- The AGPSS Transaction/Job Logic ---

def job_process(env, mac, cam, job_id, priority):
    """
    Represents the flow of a single job (transaction) through the simulation.
    """
    
    # 1. ARRIVE queue (queue is implied by requesting a resource)
    # The initial 'GOTO arr, 0.9' and 'LET PRIORITY=1' from GENERATE 
    # is handled in the generator function below.
    
    # --- MAC Facility Section (arr, queue) ---
    
    arrival_time = env.now
    
    # Request a unit of 'mac' (Enter mac, 1)
    with mac.request(priority=priority) as req:
        yield req
        
        # DEPART queue (job has started service)
        
        # ADVANCE FN$XPDIS*0.75
        service_time = xpon_dist(ADVANCE_SERVICE_MEAN)
        yield env.timeout(service_time)
        
        # GOTO noerr, 0.99 (99% chance of no error)
        if random.random() < 0.99:
            # noerr: LEAVE mac, 1
            pass # Already in the 'with' block, the 'release' happens implicitly later
        else:
            # ADVANCE 15,2 (Error time, likely normal dist)
            error_time = normal_dist(ADVANCE_SERVICE_ERR_MEAN, ADVANCE_SERVICE_ERR_DEV)
            yield env.timeout(error_time)
            # noerr is effectively reached after error correction
        
    # LEAVE mac, 1 (Release the resource)
    
    # GOTO znt, 0.5 (50% chance to go to 'znt' branch)
    if random.random() < 0.5:
        # --- ZNT Branch ---
        
        # ASSEMBLE 200 (Represents a batch/wait step, but SimPy only
        # handles the current transaction, so we model the flow time)
        
        # ARRIVE quet
        # ENTER cam, 1
        with cam.request(priority=0) as req_cam: # No priority specified, use default 0
            yield req_cam
            
            # DEPART quet
            
            # ADVANCE 372.5, 2.5 (Normal dist for CAM processing)
            cam_time = normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV)
            yield env.timeout(cam_time)
            
        # LEAVE cam, 1
        
    else:
        # --- Default Branch ---
        
        # ASSEMBLE 200 (Model flow time)
        
        # ARRIVE queo
        # ENTER cam, 1
        with cam.request(priority=0) as req_cam: # No priority specified, use default 0
            yield req_cam
            
            # DEPART queo
            
            # ADVANCE 372.5, 2.5 (Normal dist for CAM processing)
            cam_time = normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV)
            yield env.timeout(cam_time)
            
        # LEAVE cam, 1
    
    # goto: TERMINATE (End of the job process)
    # Total time in system can be calculated here if needed.
    
    finish_time = env.now
    # print(f"Job {job_id} finished at {finish_time:.2f}. Total time: {finish_time - arrival_time:.2f}")


# --- The GENERATE/Source Functions ---

def job_generator(env, mac, cam):
    """
    Generates jobs according to the GENERATE block (Poisson arrivals).
    GENERATE 0.15, 0.05, , 10000, 0
    Inter-arrival time = U[0.15 - 0.05, 0.15 + 0.05] = U[0.10, 0.20]
    Max jobs = 10000. Start time = 0.
    """
    job_id = 0
    max_jobs = 10000
    
    while job_id < max_jobs:
        job_id += 1
        
        # Inter-arrival time (AGPSS often uses Uniform for GENERATE A,B)
        time_to_next = random.uniform(0.15 - 0.05, 0.15 + 0.05)
        yield env.timeout(time_to_next)
        
        # GENERATE logic flow:
        # GOTO arr, 0.9 (90% chance to follow 'arr' path)
        if random.random() < 0.9:
            # LET PRIORITY=1
            priority = 1
        else:
            # Implicitly a TERMINATE or default path, but the structure
            # suggests all generated jobs follow a path. We'll assume the
            # 10% not going to 'arr' have default priority 0.
            priority = 0

        # Start the job process
        env.process(job_process(env, mac, cam, job_id, priority))


def run_simulation(until_time):
    """
    Sets up the environment and runs the simulation.
    SIMULATE 1,A -> Only one run (replication)
    START 1 -> Run 1 termination count (handled by max jobs)
    GENERATE 1440 TERMINATE 1 -> This is a secondary transaction/timer 
                                 to stop the simulation at time 1440.
    """
    
    print("--- Starting SimPy AGPSS Conversion ---")
    
    # Create the SimPy environment
    env = simpy.Environment()
    
    # Create the resources (facilities)
    mac = simpy.PriorityResource(env, capacity=MAC_CAPACITY)
    cam = simpy.PriorityResource(env, capacity=CAM_CAPACITY)
    
    # Start the job generator
    env.process(job_generator(env, mac, cam))
    
    # Run the simulation until the specified time
    env.run(until=until_time)
    
    print(f"--- Simulation Finished at Time {env.now} ---")
    
    # In a real simulation, you would collect and report statistics here
    # (e.g., resource utilization, queue lengths, job wait times, etc.)
    

# --- Execution ---
if __name__ == '__main__':
    # TERMINATE 1 is linked to GENERATE 1440, stopping the simulation at time 1440
    SIMULATION_TIME = 1440
    random.seed(42) # For reproducibility (AGPSS 'SIMULATE 1,A' implies a single run)
    
    run_simulation(SIMULATION_TIME)