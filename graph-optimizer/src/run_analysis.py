import sys
from pathlib import Path

# 1. Setup paths FIRST before importing custom modules
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))

# TRACE folder ka absolute root base nikalne ke liye
trace_root = current_dir.parent.parent.resolve()
sys.path.insert(0, str(trace_root / "multigraph-builder" / "src"))

# 2. Now import the modules safely
import optuna
from build_graph import load_graph
from ground_truth import load_ground_truth, split_by_date
from optimize import run_optimization

def main():
    # 3. Resolve clean absolute paths using trace_root
    graph_path = (trace_root / "multigraph-builder" / "output" / "unified_graph.json").resolve()
    ground_truth_path = (current_dir.parent / "data" / "ground_truth.json").resolve()
    
    split_date = "2024-01-01"
    n_trials = 100
    k = 5

    print("--- Optuna Visualization Runner ---")
    print(f"Loading graph from: {graph_path}")
    
    if not graph_path.exists():
        print(f"\n[ERROR] Graph file nahi mili at: {graph_path}")
        print("Please check: Kya aapne 'multigraph-builder' chalakar 'unified_graph.json' generate kiya hai?")
        return
        
    G = load_graph(graph_path)
    
    print(f"Loading ground truth from: {ground_truth_path}")
    if not ground_truth_path.exists():
        print(f"\n[ERROR] Ground truth file nahi mili at: {ground_truth_path}")
        return
        
    all_pairs = load_ground_truth(ground_truth_path)
    train_pairs, _ = split_by_date(all_pairs, split_date)
    
    if not train_pairs:
        print("ERROR: No training pairs found. Adjust dates or check file paths.")
        return

    # 4. Fire the exact optimization loop from your optimize.py module
    print(f"\nRunning TPE optimization loop ({n_trials} trials)...")
    study = run_optimization(G, train_pairs, n_trials=n_trials, k=k)
    
    # 5. Generate and save the interactive HTML optimization charts
    print("\nGenerating Optuna visualization charts...")
    
    # Ensure output folder exists
    output_dir = current_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Chart 1: Optimization History
    fig_history = optuna.visualization.plot_optimization_history(study)
    fig_history.write_html(output_dir / "optuna_history.html")
    print(f" Saved: {output_dir / 'optuna_history.html'}")
    
    # Chart 2: Hyperparameter Importance
    fig_importance = optuna.visualization.plot_param_importances(study)
    fig_importance.write_html(output_dir / "optuna_importance.html")
    print(f" Saved: {output_dir / 'optuna_importance.html'}")
    
    print("\nProcess complete! Open the generated HTML files in your browser.")

if __name__ == "__main__":
    main()
