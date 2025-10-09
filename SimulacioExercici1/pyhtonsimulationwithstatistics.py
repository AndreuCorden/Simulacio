import simpy
import random
import math
from collections import deque

# --- Setup: Global Parameters and Functions ---

MAC_CAPACITY = 6
CAM_CAPACITY = 12
SIMULATION_TIME = 1440
BATCH_SIZE = 200 # The value from ASSEMBLE 200

# ADVANCE time parameters
ADVANCE_SERVICE_MEAN = 0.75
ADVANCE_SERVICE_ERR_MEAN = 15
ADVANCE_SERVICE_ERR_DEV = 2
ADVANCE_CAM_MEAN = 372.5
ADVANCE_CAM_DEV = 2.5

# Helper functions for distributions
def xpon_dist(mean):
    return random.expovariate(1.0 / mean)

def normal_dist(mean, stdev):
    return max(0, random.gauss(mean, stdev))

# --- NEW: Batch Assembler Class for ASSEMBLE 200 ---

class BatchAssembler:
    """Manages the synchronization for a batch of BATCH_SIZE jobs."""
    def __init__(self, env, name, batch_size):
        self.env = env
        self.name = name
        self.batch_size = batch_size
        self.waiting_jobs = []
        self.batch_count = 0
        self.release_event = self.env.event() # Event to trigger batch release

    def assemble(self, job_id):
        """Job process calls this to wait for the batch to fill."""
        self.batch_count += 1
        self.waiting_jobs.append(job_id)
        
        # Check if the batch is full
        if self.batch_count >= self.batch_size:
            # 1. Store the event for jobs currently waiting
            release = self.release_event
            
            # 2. Reset the state for the *next* batch
            self.batch_count = 0
            self.release_event = self.env.event()
            
            # 3. Trigger the event to release the current batch
            release.succeed()
            
        # Wait for the current batch's release event
        return self.release_event

# --- Statistics Collector Class (Minor Update) ---

class StatisticsCollector:
    def __init__(self, env):
        self.env = env
        self.jobs_generated = 0
        self.jobs_terminated = 0
        self.priority_1_count = 0 # New stat from last request
        
        self.mac_wait_times = []
        self.cam_wait_times = []
        self.system_times = [] 
        
        # State Monitoring (Time-Weighted Averages)
        self.queue_mac_length = [(0, 0)]
        self.queue_cam_o_length = [(0, 0)] 
        self.queue_cam_t_length = [(0, 0)]
        
        self.assembled_batches = 0 # Now tracks batches completed, not individual items

    def record_queue_length(self, queue_list, length):
        if not queue_list or queue_list[-1][1] != length:
             queue_list.append((self.env.now, length))
             
    def calculate_time_weighted_average(self, data_list):
        if len(data_list) <= 1:
            return 0
        total_area = 0
        total_time = self.env.now
        
        for i in range(len(data_list) - 1):
            time_start, value = data_list[i]
            time_end = data_list[i+1][0]
            total_area += value * (time_end - time_start)
            
        last_value = data_list[-1][1]
        last_time = data_list[-1][0]
        total_area += last_value * (total_time - last_time)

        return total_area / total_time if total_time > 0 else 0

    def report(self):
        """Prints the final statistics."""
        print("\n--- Simulation Statistics ---")
        print(f"Total Simulation Time: {self.env.now:.2f}")
        print("-" * 35)

        # 1. REMAINING ELEMENTS CALCULATION
        mac_in_queue = len(self.mac.queue)
        mac_in_service = self.mac.count
        cam_in_queue = len(self.cam.queue)
        cam_in_service = self.cam.count
        
        # Elements waiting at the ASSEMBLE points
        assemble_o_waiting = self.queo_assembler.batch_count
        assemble_t_waiting = self.quet_assembler.batch_count
        
        total_remaining = (mac_in_queue + mac_in_service + 
                           cam_in_queue + cam_in_service +
                           assemble_o_waiting + assemble_t_waiting)
        
        print(f"1. TOTAL ELEMENTS REMAINING IN SYSTEM: {total_remaining}")
        print("   - MAC Queue (waiting):", mac_in_queue)
        print("   - MAC Service (in use):", mac_in_service)
        print("   - CAM Queue (waiting):", cam_in_queue)
        print("   - CAM Service (in use):", cam_in_service)
        print(f"   - ASSEMBLE (queo) Waiting: {assemble_o_waiting}")
        print(f"   - ASSEMBLE (quet) Waiting: {assemble_t_waiting}")
        print("-" * 35)
        
        # Throughput
        print(f"2. Jobs Generated: {self.jobs_generated}")
        print(f"3. Jobs Terminated: {self.jobs_terminated}")
        print(f"4. Total Batches (200 items) Assembled: {self.assembled_batches}")
        
        # ... (rest of the report is similar)
        print("\n--- Time-Weighted Averages and Wait Times ---")
        
        self.record_queue_length(self.queue_mac_length, len(self.mac.queue))
        self.record_queue_length(self.queue_cam_o_length, len(self.cam.queue)) 
        
        avg_mac_queue = self.calculate_time_weighted_average(self.queue_mac_length)
        avg_cam_queue = self.calculate_time_weighted_average(self.queue_cam_o_length)
        
        print(f"5. Average MAC Queue Size: {avg_mac_queue:.3f}")
        print(f"6. Average CAM Queue Size: {avg_cam_queue:.3f}")
        
        if self.mac_wait_times:
            print(f"7. Average MAC Wait Time: {sum(self.mac_wait_times) / len(self.mac_wait_times):.3f}")
        if self.system_times:
            print(f"8. Average Total Time in System: {sum(self.system_times) / len(self.system_times):.3f}")
            
        print("\n--- Custom Logic Statistics ---")
        print(f"9. Total Instances assigned Priority 1: {self.priority_1_count}")


# --- The AGPSS Transaction/Job Logic (Crucially Updated) ---

def job_process(env, mac, cam, stats, job_id, priority, queo_assembler, quet_assembler):
    """Represents the flow of a single job (transaction) through the simulation."""
    
    arrival_time = env.now
    
    # 1. MAC Facility Section (arr, queue)
    stats.record_queue_length(stats.queue_mac_length, len(mac.queue))
    mac_wait_start = env.now

    with mac.request(priority=priority) as req:
        yield req
        
        stats.mac_wait_times.append(env.now - mac_wait_start)
        stats.record_queue_length(stats.queue_mac_length, len(mac.queue))
        
        # Service
        yield env.timeout(xpon_dist(ADVANCE_SERVICE_MEAN))
        
        # Error check 
        if random.random() >= 0.99:
            yield env.timeout(normal_dist(ADVANCE_SERVICE_ERR_MEAN, ADVANCE_SERVICE_ERR_DEV))
            
    # LEAVE mac, 1

    # 2. CAM Facility Section
    cam_wait_start = env.now
    
    # GOTO znt, 0.5 (50% chance to go to 'znt' branch)
    if random.random() < 0.5:
        # --- ZNT Branch (quet) ---
        
        # ASSEMBLE 200 (Wait until 200 items arrive here)
        yield quet_assembler.assemble(job_id)
        if quet_assembler.batch_count == 0:
             # Only one job from the batch needs to increment the batch counter
             stats.assembled_batches += 1
        
        # ARRIVE quet
        stats.record_queue_length(stats.queue_cam_t_length, len(cam.queue))
        
        # ENTER cam, 1
        with cam.request(priority=0) as req_cam:
            yield req_cam
            
            stats.cam_wait_times.append(env.now - cam_wait_start)
            stats.record_queue_length(stats.queue_cam_t_length, len(cam.queue))
            
            # ADVANCE 372.5, 2.5
            yield env.timeout(normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV))
            
    else:
        # --- Default Branch (queo) ---
        
        # ASSEMBLE 200
        yield queo_assembler.assemble(job_id)
        if queo_assembler.batch_count == 0:
             # Only one job from the batch needs to increment the batch counter
             stats.assembled_batches += 1

        # ARRIVE queo
        stats.record_queue_length(stats.queue_cam_o_length, len(cam.queue))
        
        # ENTER cam, 1
        with cam.request(priority=0) as req_cam:
            yield req_cam
            
            stats.cam_wait_times.append(env.now - cam_wait_start)
            stats.record_queue_length(stats.queue_cam_o_length, len(cam.queue))
            
            # ADVANCE 372.5, 2.5
            yield env.timeout(normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV))
            
    # TERMINATE
    finish_time = env.now
    stats.jobs_terminated += 1
    stats.system_times.append(finish_time - arrival_time)


# --- The GENERATE/Source Functions ---

def job_generator(env, mac, cam, stats, queo_assembler, quet_assembler):
    """Generates jobs."""
    job_id = 0
    max_jobs = 10000
    
    while job_id < max_jobs:
        job_id += 1
        stats.jobs_generated += 1
        
        time_to_next = random.uniform(0.15 - 0.05, 0.15 + 0.05)
        yield env.timeout(time_to_next)
        
        # GOTO arr, 0.9 (10% chance for Priority 1)
        if random.random() <= 0.1:
            priority = 1
            stats.priority_1_count += 1
        else:
            priority = 0

        # Pass the assembler objects to the job process
        env.process(job_process(env, mac, cam, stats, job_id, priority, 
                                queo_assembler, quet_assembler))


def run_simulation(until_time):
    """Sets up the environment and runs the simulation."""
    
    print("--- Starting SimPy AGPSS Conversion with Batching ---")
    
    env = simpy.Environment()
    
    mac = simpy.PriorityResource(env, capacity=MAC_CAPACITY)
    cam = simpy.PriorityResource(env, capacity=CAM_CAPACITY)
    
    # --- NEW: Assembler Instances ---
    queo_assembler = BatchAssembler(env, 'queo', BATCH_SIZE)
    quet_assembler = BatchAssembler(env, 'quet', BATCH_SIZE)
    
    stats = StatisticsCollector(env)
    stats.mac = mac
    stats.cam = cam
    # Pass assembler instances to stats for final reporting of waiting count
    stats.queo_assembler = queo_assembler
    stats.quet_assembler = quet_assembler
    
    # Start the generator, passing the assemblers
    env.process(job_generator(env, mac, cam, stats, queo_assembler, quet_assembler))
    
    env.run(until=until_time)
    
    print(f"--- Simulation Run Complete at Time {env.now:.2f} ---")
    
    stats.report()

# --- Execution ---
if __name__ == '__main__':
    random.seed(42) 
    run_simulation(SIMULATION_TIME)