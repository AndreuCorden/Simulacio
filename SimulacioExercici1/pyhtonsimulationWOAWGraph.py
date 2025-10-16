import simpy
import random
import math
import matplotlib.pyplot as plt # --- NEW IMPORT ---

# --- Global Parameters ---

MAC_CAPACITY = 6
CAM_CAPACITY = 12
SIMULATION_TIME = 1440
BATCH_SIZE = 200 

# ADVANCE time parameters
ADVANCE_SERVICE_MEAN = 0.75
ADVANCE_SERVICE_ERR_MEAN = 15
ADVANCE_SERVICE_ERR_DEV = 2
ADVANCE_CAM_MEAN = 372.5
ADVANCE_CAM_DEV = 2.5

# NOTE: These global counters are necessary for the desired 'lossy' CAM logic
ASSEMBLEQUEO = 0
ASSEMBLEQUET = 0

# --- Helper Functions for Distributions ---

def xpon_dist(mean):
    # The rate is 1.0 / mean
    return random.expovariate(1.0 / mean)

def normal_dist(mean, stdev):
    # Ensures time cannot be negative
    return max(0, random.gauss(mean, stdev))

# --- Batch Assembler Class (Kept but not used in job_process) ---

class BatchAssembler:
    def __init__(self, env, name, batch_size, stats): 
        self.env = env
        self.name = name
        self.batch_size = batch_size
        self.stats = stats 
        self.waiting_jobs = [] 
        self.batch_count = 0
        self.release_event = self.env.event() 

    # NOTE: This assemble method is not called in the job_process below, 
    # preserving the previous 'lossy' CAM logic.
    def assemble(self, job_id, queue_list): 
        # This implementation is not used for CAM logic, preserving original flow
        pass 

# --- Statistics Collector Class (MODIFIED for Utilization & Graphs) ---

class StatisticsCollector:
    def __init__(self, env):
        self.env = env
        self.jobs_generated = 0
        self.jobs_terminated = 0
        self.priority_1_count = 0
        
        # Lists for calculating average wait times
        self.mac_wait_times = []
        self.queo_wait_times = [] 
        self.quet_wait_times = [] 
        self.cam_wait_times = []
        self.system_times = [] 
        
        # Lists for calculating time-weighted average queue length
        self.queue_mac_length = [(0, 0)]
        self.queue_queo_length = [(0, 0)] 
        self.queue_quet_length = [(0, 0)] 
        
        # NOTE: Manual lists must be tracked by job_process for the 'lossy' logic
        self.queo_wait_list = []
        self.quet_wait_list = []
        
        # --- NEW: Utilization Tracking ---
        self.mac_usage = [(0, 0)] # (time, count)
        self.cam_usage = [(0, 0)] # (time, count)
        # -----------------------------------

    def record_queue_length(self, queue_list, waiting_jobs_list, is_cam_queue=False):
        
        length = len(waiting_jobs_list)
        
        # For CAM, we calculate blocks based on jobs in the waiting list
        if is_cam_queue:
            length = math.ceil(length / BATCH_SIZE) if length > 0 else 0
        
        if not queue_list or queue_list[-1][1] != length:
             queue_list.append((self.env.now, length))
             
    def record_queue_length_blocks(self, queue_list, waiting_jobs_list):
        # NOTE: This function is preserved from the previous attempt but is 
        # now redundant since record_queue_length handles CAM queues. 
        # It's kept for minimal code change.
        self.record_queue_length(queue_list, waiting_jobs_list, is_cam_queue=True)
             
    # --- NEW: Utilization Monitor ---
    def monitor_utilization(self):
        """Records the number of units currently in use for MAC and CAM."""
        while True:
            # Record MAC count
            if not self.mac_usage or self.mac_usage[-1][1] != self.mac.count:
                self.mac_usage.append((self.env.now, self.mac.count))
            
            # Record CAM count
            if not self.cam_usage or self.cam_usage[-1][1] != self.cam.count:
                self.cam_usage.append((self.env.now, self.cam.count))
                
            yield self.env.timeout(1) # Check state every 1 time unit or small interval
    # ---------------------------------

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

    # --- NEW: Graph Generation Method ---
    def generate_graphs(self):
        
        # Define the statistics to plot
        plot_data = {
            "MAC Facility Utilization (Units in Use)": (self.mac_usage, MAC_CAPACITY, "Units in Use"),
            "CAM Facility Utilization (Units in Use)": (self.cam_usage, CAM_CAPACITY, "Units in Use"),
            "MAC Queue Length (Jobs)": (self.queue_mac_length, None, "Jobs Waiting"),
            "CAM QUEO Queue Length (Blocks)": (self.queue_queo_length, None, "Blocks Waiting"),
            "CAM QUET Queue Length (Blocks)": (self.queue_quet_length, None, "Blocks Waiting"),
        }
        
        for title, (data_list, capacity, ylabel) in plot_data.items():
            
            if not data_list or len(data_list) < 2:
                print(f"Skipping plot for {title}: Insufficient data.")
                continue

            times = [item[0] for item in data_list]
            values = [item[1] for item in data_list]

            plt.figure(figsize=(10, 5))
            # Use 'post' step function for SimPy state changes
            plt.step(times, values, where='post') 
            
            # Add capacity line for utilization plots
            if "Utilization" in title:
                plt.axhline(capacity, color='r', linestyle='--', label=f'Capacity ({capacity} Units)')
                plt.legend()
            
            # Add average line for queue length plots
            elif "Queue" in title:
                avg = self.calculate_time_weighted_average(data_list)
                plt.axhline(avg, color='g', linestyle='--', label=f'Avg: {avg:.3f}')
                plt.legend()

            plt.title(f"{title} over Time")
            plt.xlabel("Simulation Time")
            plt.ylabel(ylabel)
            plt.grid(True, linestyle=':', alpha=0.6)
            plt.show()
    # -----------------------------------

    def report(self):
        # NOTE: queue_queo_length and queue_quet_length must be recorded one final time 
        # before calculation using the global self.queo_wait_list/self.quet_wait_list
        self.record_queue_length(self.queue_mac_length, self.mac.queue)
        self.record_queue_length(self.queue_queo_length, self.queo_wait_list, is_cam_queue=True)
        self.record_queue_length(self.queue_quet_length, self.quet_wait_list, is_cam_queue=True)
        
        print("\n" + "="*50)
        print(" SIMULATION STATISTICS REPORT ".center(50, ' '))
        print("="*50)
        print(f"Total Simulation Time: {self.env.now:.2f}")
        print("-" * 50)

        # 1. REMAINING ELEMENTS CALCULATION (Jobs)
        mac_in_queue = len(self.mac.queue)
        mac_in_service = self.mac.count
        
        queo_in_queue_jobs = len(self.queo_wait_list) # Use the manual list
        quet_in_queue_jobs = len(self.quet_wait_list) # Use the manual list
        cam_in_service = self.cam.count 

        cam_in_queue_queo_blocks = math.ceil(queo_in_queue_jobs / BATCH_SIZE) if queo_in_queue_jobs > 0 else 0
        cam_in_queue_quet_blocks = math.ceil(quet_in_queue_jobs / BATCH_SIZE) if quet_in_queue_jobs > 0 else 0
        
        # NOTE: cam_in_service * BATCH_SIZE is WRONG for the lossy logic, 
        # as only one job is holding the resource. We use self.cam.count * 1
        total_remaining = (mac_in_queue + mac_in_service + 
                           queo_in_queue_jobs + quet_in_queue_jobs + 
                           cam_in_service) 
        
        print(f"1. TOTAL ELEMENTS REMAINING IN SYSTEM (Jobs): {total_remaining}")
        print("   - MAC Queue (waiting jobs):", mac_in_queue)
        print("   - MAC Service (in use jobs):", mac_in_service)
        print(f"   - CAM QUEO Waiting (jobs): {queo_in_queue_jobs} ({cam_in_queue_queo_blocks} blocks)")
        print(f"   - CAM QUET Waiting (jobs): {quet_in_queue_jobs} ({cam_in_queue_quet_blocks} blocks)")
        print(f"   - CAM Service (in use jobs): {cam_in_service}") # Changed to cam_in_service
        print(f"   - Elements in QUEO: {ASSEMBLEQUEO}")
        
        print(f"   - Elements in QUET: {ASSEMBLEQUET}")
        print("-" * 50)
        
        print(f"2. Jobs Generated: {self.jobs_generated}")
        print(f"3. Jobs Terminated: {self.jobs_terminated}")
        
        
        print("\n--- Time-Weighted Averages and Wait Times ---")
        
        avg_mac_queue = self.calculate_time_weighted_average(self.queue_mac_length)
        avg_queo_queue = self.calculate_time_weighted_average(self.queue_queo_length)
        avg_quet_queue = self.calculate_time_weighted_average(self.queue_quet_length)
        
        if self.queo_wait_times:
            print(f"4.1 Average time in CAM QUEO (Jobs that waited): {sum(self.queo_wait_times) / len(self.queo_wait_times):.3f}")
        if self.quet_wait_times:
            print(f"4.2 Average time in CAM QUET (Jobs that waited): {sum(self.quet_wait_times) / len(self.quet_wait_times):.3f}")
            
        print(f"5. Average MAC Queue Size (Jobs): {avg_mac_queue:.3f}")
        print(f"6. Average CAM QUEO Queue Size (Blocks): {avg_queo_queue:.3f}")
        print(f"7. Average CAM QUET Queue Size (Blocks): {avg_quet_queue:.3f}")

        if self.mac_wait_times:
            print(f"8. Average MAC Wait Time: {sum(self.mac_wait_times) / len(self.mac_wait_times):.3f}")
        if self.system_times:
            print(f"9. Average Total Time in System: {sum(self.system_times) / len(self.system_times):.3f}")
            
        print("\n--- Utilization Statistics ---")
        
        avg_mac_in_use = self.calculate_time_weighted_average(self.mac_usage)
        avg_cam_in_use = self.calculate_time_weighted_average(self.cam_usage)
        
        mac_utilization = (avg_mac_in_use / MAC_CAPACITY) * 100
        cam_utilization = (avg_cam_in_use / CAM_CAPACITY) * 100
        
        print(f"10. Average MAC Utilization: {mac_utilization:.2f}% (Average {avg_mac_in_use:.3f} out of {MAC_CAPACITY} units in use)")
        print(f"11. Average CAM Utilization: {cam_utilization:.2f}% (Average {avg_cam_in_use:.3f} out of {CAM_CAPACITY} units in use)")
            
        print("\n--- Custom Logic Statistics ---")
        print(f"12. Total Instances assigned Priority 1: {self.priority_1_count}")
        print("="*50)


# --- The AGPSS Transaction/Job Logic (ORIGINAL, REVERTED) ---

def job_process(env, mac, cam, stats, job_id, priority, queo_assembler, quet_assembler):
    
    global ASSEMBLEQUEO
    global ASSEMBLEQUET

    arrival_time = env.now
    
    # 1. MAC Facility Section
    stats.record_queue_length(stats.queue_mac_length, mac.queue)
    mac_wait_start = env.now

    with mac.request(priority=priority) as req:
        yield req
        
        stats.mac_wait_times.append(env.now - mac_wait_start)
        stats.record_queue_length(stats.queue_mac_length, mac.queue)
        
        yield env.timeout(xpon_dist(ADVANCE_SERVICE_MEAN))
        
        if random.random() >= 0.99:
            yield env.timeout(normal_dist(ADVANCE_SERVICE_ERR_MEAN, ADVANCE_SERVICE_ERR_DEV))
            
    # 2. CAM Facility Section (ORIGINAL LOSS-BASED LOGIC)
    
    cam_wait_start = env.now # Wait starts here
    
    if random.random() < 0.5:
        # --- ZNT Branch (quet) ---
        
        ASSEMBLEQUET += 1

        if ASSEMBLEQUET == BATCH_SIZE: # Only the 200th job proceeds
            
            ASSEMBLEQUET = 0
            
            # ARRIVE quet (The 200th job is the only one to record and process)
            stats.quet_wait_list.append(job_id) # Add job to track waiting for this batch
            quet_start_time = env.now
            stats.record_queue_length(stats.queue_quet_length, stats.quet_wait_list, is_cam_queue=True)

            with cam.request(priority=0) as req_cam:
                yield req_cam
                
                # Job is processed, remove from manual list 
                stats.quet_wait_times.append(env.now - quet_start_time)
                stats.quet_wait_list.remove(job_id)
                stats.cam_wait_times.append(env.now - cam_wait_start)
                stats.record_queue_length(stats.queue_quet_length, stats.quet_wait_list, is_cam_queue=True)
                
                yield env.timeout(normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV))
                
            # TERMINATE
            finish_time = env.now
            stats.jobs_terminated += 1 # Only this one job terminates, 199 are lost
            stats.system_times.append(finish_time - arrival_time)
        # else: 199 jobs are implicitly 'lost' (they exit the process without yielding/terminating)
            
    else:
        # --- Default Branch (queo) ---
        
        ASSEMBLEQUEO += 1

        if ASSEMBLEQUEO == BATCH_SIZE: # Only the 200th job proceeds
            
            ASSEMBLEQUEO = 0

            # ARRIVE queo
            stats.queo_wait_list.append(job_id)
            quet_start_time = env.now # This is queo_start_time, but kept for minimal change
            stats.record_queue_length(stats.queue_queo_length, stats.queo_wait_list, is_cam_queue=True)
            
            with cam.request(priority=0) as req_cam:
                yield req_cam
                
                # Job is processed, remove from manual list
                stats.queo_wait_times.append(env.now - cam_wait_start) # Use cam_wait_start for consistency
                stats.queo_wait_list.remove(job_id)
                stats.cam_wait_times.append(env.now - cam_wait_start)
                stats.record_queue_length(stats.queue_queo_length, stats.queo_wait_list, is_cam_queue=True)
                
                yield env.timeout(normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV))
            # TERMINATE
            finish_time = env.now
            stats.jobs_terminated += 1
            stats.system_times.append(finish_time - arrival_time)
        # else: 199 jobs are implicitly 'lost'

# --- The GENERATE/Source Functions (Unchanged) ---

def job_generator(env, mac, cam, stats, queo_assembler, quet_assembler):
    """Generates jobs."""
    job_id = 0
    max_jobs = 10000
    
    while job_id < max_jobs:
        job_id += 1
        stats.jobs_generated += 1
        
        # GENERATE (0.15, 0.05)
        time_to_next = random.uniform(0.15 - 0.05, 0.15 + 0.05)
        yield env.timeout(time_to_next)
        
        # LET PRIORITY=1 (10% chance)
        if random.random() <= 0.1:
            priority = 1
            stats.priority_1_count += 1
        else:
            priority = 0

        env.process(job_process(env, mac, cam, stats, job_id, priority, 
                                 queo_assembler, quet_assembler))


def run_simulation(until_time):
    """Sets up the environment and runs the simulation."""
    
    print("--- Starting SimPy AGPSS Conversion with Corrected Batching Logic ---")

    env = simpy.Environment()
    
    # Resources
    mac = simpy.PriorityResource(env, capacity=MAC_CAPACITY)
    cam = simpy.PriorityResource(env, capacity=CAM_CAPACITY)
    
    # Stats and Assemblers
    stats = StatisticsCollector(env)
    # The assemblers are initialized but intentionally unused in job_process
    queo_assembler = BatchAssembler(env, 'queo', BATCH_SIZE, stats)
    quet_assembler = BatchAssembler(env, 'quet', BATCH_SIZE, stats)
    
    # Pass resources and assemblers to stats for reporting
    stats.mac = mac
    stats.cam = cam
    stats.queo_assembler = queo_assembler
    stats.quet_assembler = quet_assembler
    
    # Start Utilization Monitor
    env.process(stats.monitor_utilization())
    
    # Start generator
    env.process(job_generator(env, mac, cam, stats, queo_assembler, quet_assembler))
    
    # Run simulation
    env.run(until=until_time)
    
    print(f"--- Simulation Run Complete at Time {env.now:.2f} ---")
    
    stats.report()
    
    # --- NEW: Generate Graphs ---
    stats.generate_graphs()
    # ----------------------------

# --- Execution ---
if __name__ == '__main__':
    random.seed(42) 
    run_simulation(SIMULATION_TIME)
