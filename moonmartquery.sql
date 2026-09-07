.schema batch_inventory;
.schema products;


-- Fix 'CURRENT_TIMESTAMP' text issue
/*.mode csv
.nullvalue ""
.import your_file.csv batch_inventory*/