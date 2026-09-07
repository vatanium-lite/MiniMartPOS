.fullschema

SELECT * FROM sales_transactions;

-- Fix 'CURRENT_TIMESTAMP' text issue
/*.mode csv
.nullvalue ""
.import your_file.csv batch_inventory*/