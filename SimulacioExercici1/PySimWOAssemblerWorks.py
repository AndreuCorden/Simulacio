import simpy
import random
import math

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

ASSEMBLEQUEO = 0
ASSEMBLEQUET = 0

# --- Helper Functions for Distributions ---

def xpon_dist(mean):
    return random.expovariate(1.0 / mean)

def normal_dist(mean, stdev):
    return max(0, random.gauss(mean, stdev))

# --- Batch Assembler Class (Uses the corrected batch counting) ---

class BatchAssembler:
    def __init__(self, env, name, batch_size, stats): 
        self.env = env
        self.name = name
        self.batch_size = batch_size
        self.stats = stats # Store stats object
        self.waiting_jobs = []
        self.batch_count = 0
        self.release_event = self.env.event() 

    def assemble(self, job_id):
        self.batch_count += 1
        self.waiting_jobs.append(job_id)
        
        if self.batch_count >= self.batch_size:
            release = self.release_event
            
            # CRITICAL FIX: Increment the assembled batch count here, once per batch
            self.stats.assembled_batches += 1 
            
            # Reset for the next batch
            self.batch_count = 0
            self.release_event = self.env.event()
            
            release.succeed()
            
        return self.release_event

# --- Statistics Collector Class ---

class StatisticsCollector:
    def __init__(self, env):
        self.env = env
        self.jobs_generated = 0
        self.jobs_terminated = 0
        self.priority_1_count = 0
        
        self.queo_wait_list = [] 
        self.quet_wait_list = [] 
        
        self.mac_wait_times = []
        self.queo_wait_times = []
        self.quet_wait_times = []
        self.cam_wait_times = []
        self.system_times = [] 
        
        self.queue_mac_length = [(0, 0)]
        self.queue_queo_length = [(0, 0)] 
        self.queue_quet_length = [(0, 0)] 


    def record_queue_length(self, queue_list, waiting_jobs_list, is_cam_queue=False):
        
        length = len(waiting_jobs_list)
        
        if is_cam_queue and length > 0:
            length = math.ceil(length / BATCH_SIZE)
        
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
        print("\n" + "="*50)
        print(" SIMULATION STATISTICS REPORT ".center(50, ' '))
        print("="*50)
        print(f"Total Simulation Time: {self.env.now:.2f}")
        print("-" * 50)

        # 1. REMAINING ELEMENTS CALCULATION
        mac_in_queue = len(self.mac.queue)
        mac_in_service = self.mac.count
        
        queo_in_queue_jobs = len(self.queo_wait_list)
        quet_in_queue_jobs = len(self.quet_wait_list)
        cam_in_queue_jobs = queo_in_queue_jobs + quet_in_queue_jobs
        
        cam_in_queue_queo_blocks = math.ceil(queo_in_queue_jobs / BATCH_SIZE) if queo_in_queue_jobs > 0 else 0
        cam_in_queue_quet_blocks = math.ceil(quet_in_queue_jobs / BATCH_SIZE) if quet_in_queue_jobs > 0 else 0
        
        cam_in_service = self.cam.count 

        assemble_o_waiting = self.queo_assembler.batch_count
        assemble_t_waiting = self.quet_assembler.batch_count
        
        total_remaining = (mac_in_queue + mac_in_service + 
                           cam_in_queue_jobs + cam_in_service + 
                           assemble_o_waiting + assemble_t_waiting)
        
        print(f"1. TOTAL ELEMENTS REMAINING IN SYSTEM (Jobs): {total_remaining}")
        print("   - MAC Queue (waiting jobs):", mac_in_queue)
        print("   - MAC Service (in use jobs):", mac_in_service)
        print(f"   - CAM QUEO Queue (blocks): {cam_in_queue_queo_blocks} ({queo_in_queue_jobs} jobs)")
        print(f"   - CAM QUET Queue (blocks): {cam_in_queue_quet_blocks} ({quet_in_queue_jobs} jobs)")
        print("   - CAM Service (in use jobs):", cam_in_service)
        print(f"   - Elements in QUEO: {ASSEMBLEQUEO}")
        
        print(f"   - Elements in QUET: {ASSEMBLEQUET}")
        print("-" * 50)
        
        print(f"2. Jobs Generated: {self.jobs_generated}")
        print(f"3. Jobs Terminated: {self.jobs_terminated}")
        
        
        print("\n--- Time-Weighted Averages and Wait Times ---")
        
        self.record_queue_length(self.queue_mac_length, self.mac.queue)
        self.record_queue_length(self.queue_queo_length, self.queo_wait_list, is_cam_queue=True)
        self.record_queue_length(self.queue_quet_length, self.quet_wait_list, is_cam_queue=True)
        
        avg_mac_queue = self.calculate_time_weighted_average(self.queue_mac_length)
        avg_queo_queue = self.calculate_time_weighted_average(self.queue_queo_length)
        avg_quet_queue = self.calculate_time_weighted_average(self.queue_quet_length)
        
        print(f"4.1 Average time in QUEO: {sum(self.queo_wait_times) / len(self.queo_wait_times):.3f}")
        print(f"4.2 Average time in QUET: {sum(self.quet_wait_times) / len(self.quet_wait_times):.3f}")
        print(f"5. Average MAC Queue Size (Jobs): {avg_mac_queue:.3f}")
        print(f"6. Average CAM QUEO Queue Size (Blocks): {avg_queo_queue:.3f}")
        print(f"7. Average CAM QUET Queue Size (Blocks): {avg_quet_queue:.3f}")

        if self.mac_wait_times:
            print(f"8. Average MAC Wait Time: {sum(self.mac_wait_times) / len(self.mac_wait_times):.3f}")
        if self.system_times:
            print(f"9. Average Total Time in System: {sum(self.system_times) / len(self.system_times):.3f}")
            
        print("\n--- Custom Logic Statistics ---")
        print(f"10. Total Instances assigned Priority 1: {self.priority_1_count}")
        print("="*50)


# --- The AGPSS Transaction/Job Logic ---

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
            
    # 2. CAM Facility Section
    cam_wait_start = env.now
    
    if random.random() < 0.5:
        # --- ZNT Branch (quet) ---
        
        ASSEMBLEQUET += 1

        if ASSEMBLEQUET == 200:
        
            ASSEMBLEQUET = 0
            # ARRIVE quet
            stats.quet_wait_list.append(job_id)
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
            stats.jobs_terminated += 1
            stats.system_times.append(finish_time - arrival_time)
        else: 0
            
    else:
        # --- Default Branch (queo) ---
        
        ASSEMBLEQUEO += 1

        if ASSEMBLEQUEO == 200:
        
            ASSEMBLEQUEO = 0

            # ARRIVE queo
            stats.queo_wait_list.append(job_id)
            queo_start_time = env.now
            stats.record_queue_length(stats.queue_queo_length, stats.queo_wait_list, is_cam_queue=True)
        
            with cam.request(priority=0) as req_cam:
                yield req_cam
            
                # Job is processed, remove from manual list
                stats.queo_wait_times.append(env.now - queo_start_time)
                stats.queo_wait_list.remove(job_id)
                stats.cam_wait_times.append(env.now - cam_wait_start)
                stats.record_queue_length(stats.queue_queo_length, stats.queo_wait_list, is_cam_queue=True)
            
                yield env.timeout(normal_dist(ADVANCE_CAM_MEAN, ADVANCE_CAM_DEV))
            # TERMINATE
            finish_time = env.now
            stats.jobs_terminated += 1
            stats.system_times.append(finish_time - arrival_time)
            


# --- The GENERATE/Source Functions (CORRECTED Priority Logic) ---

def job_generator(env, mac, cam, stats, queo_assembler, quet_assembler):
    """Generates jobs."""
    job_id = 0
    max_jobs = 10000
    
    while job_id < max_jobs:
        job_id += 1
        stats.jobs_generated += 1
        
        time_to_next = random.uniform(0.15 - 0.05, 0.15 + 0.05)
        yield env.timeout(time_to_next)
        
        # CORRECTED: GOTO arr, 0.9 means 10% chance (1-0.9) for LET PRIORITY=1
        if random.random() <= 0.1:
            priority = 1
            stats.priority_1_count += 1
        else:
            priority = 0

        env.process(job_process(env, mac, cam, stats, job_id, priority, 
                                queo_assembler, quet_assembler))


def run_simulation(until_time):
    """Sets up the environment and runs the simulation."""
    
    print("--- Starting SimPy AGPSS Conversion with Corrected Priority ---")

    env = simpy.Environment()
    
    mac = simpy.PriorityResource(env, capacity=MAC_CAPACITY)
    cam = simpy.PriorityResource(env, capacity=CAM_CAPACITY)
    
    stats = StatisticsCollector(env)
    
    queo_assembler = BatchAssembler(env, 'queo', BATCH_SIZE, stats)
    quet_assembler = BatchAssembler(env, 'quet', BATCH_SIZE, stats)
    
    stats.mac = mac
    stats.cam = cam
    stats.queo_assembler = queo_assembler
    stats.quet_assembler = quet_assembler
    
    env.process(job_generator(env, mac, cam, stats, queo_assembler, quet_assembler))
    
    env.run(until=until_time)
    
    print(f"--- Simulation Run Complete at Time {env.now:.2f} ---")
    
    stats.report()

# --- Execution ---
if __name__ == '__main__':
    random.seed(42) 
    run_simulation(SIMULATION_TIME)
