
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_chart():
    # Setup the figure
    fig, ax = plt.subplots(figsize=(14, 6))

    # Define colors and transparency
    alpha_fill = 0.3
    alpha_line = 1.0
    
    colors = {
        'Smoke': 'grey',
        'Stress': 'blueviolet',
        'Soak': 'dodgerblue',
        'Breakpoint': 'crimson'
    }

    # Define polygons (Time, VUs)
    # Time scale: 0 to 100 roughly for plotting
    # VU scale: 0 to 10 roughly
    
    # Smoke: Very short, low load
    smoke_x = [0, 2, 4, 6, 0]
    smoke_y = [0, 2, 2, 0, 0]
    
    # Stress: Medium duration, High load (above Average)
    # Ramps up, holds, ramps down
    stress_x = [0, 10, 30, 40, 0] 
    stress_y = [0,  7,  7,  0, 0]

    # Soak: Long duration, Average load
    # Ramps up slightly slower, holds for very long
    soak_x = [0, 10, 90, 100, 0]
    soak_y = [0,  4,  4,   0, 0]

    # Breakpoint: Ramps up until it breaks (Unrealistic)
    # Goes higher than Stress
    breakpoint_x = [0, 50, 50, 0] # Ends abruptly or ramps down? Usually ramps up to failure.
    # Let's make it look like the graph: Ramps up linearly to a high point.
    # In the image, Breakpoint is the red one usually going high.
    breakpoint_y = [0, 10,  0, 0]

    # Plotting order matters for visual layering
    # Generally: Soak (back), Stress, Breakpoint, Smoke (front)
    
    # Draw Soak
    ax.fill(soak_x, soak_y, color=colors['Soak'], alpha=alpha_fill, label='Soak')
    ax.plot(soak_x, soak_y, color=colors['Soak'], alpha=alpha_line, linewidth=2)
    
    # Draw Stress
    ax.fill(stress_x, stress_y, color=colors['Stress'], alpha=alpha_fill, label='Stress')
    ax.plot(stress_x, stress_y, color=colors['Stress'], alpha=alpha_line, linewidth=2)

    # Draw Breakpoint
    ax.fill(breakpoint_x, breakpoint_y, color=colors['Breakpoint'], alpha=alpha_fill, label='Breakpoint')
    ax.plot(breakpoint_x, breakpoint_y, color=colors['Breakpoint'], alpha=alpha_line, linewidth=2)
    
    # Draw Smoke
    ax.fill(smoke_x, smoke_y, color=colors['Smoke'], alpha=alpha_fill, label='Smoke')
    ax.plot(smoke_x, smoke_y, color=colors['Smoke'], alpha=alpha_line, linewidth=2)

    # Customizing axes
    
    # X-Axis Labels
    # "Short" around 5-10, "Medium" around 40-50, "Very Long!" around 90-100
    ax.set_xticks([5, 40, 95])
    ax.set_xticklabels(['Short', 'Medium', 'Very Long!'], color='darkgrey', fontsize=12)
    
    # Y-Axis Labels
    # "Few" (Smoke level), "Average" (Soak level), "Above Average" (Stress level), "Unrealistic" (Breakpoint max)
    ax.set_yticks([2, 4, 7, 10])
    ax.set_yticklabels(['Few', 'Average', 'Above\nAverage', 'Unrealistic'], color='darkgrey', fontsize=12)

    # Main Labels
    ax.set_xlabel('Duration', loc='right', fontsize=14, color='silver', fontweight='bold')
    ax.set_ylabel('VUs/Throughput', loc='top', fontsize=14, color='silver', fontweight='bold', rotation=0)
    ax.yaxis.set_label_coords(-0.05, 1.02) # Move Y label to top left

    # Title
    ax.set_title('Load test types at a glance', fontsize=18, color='dimgrey', fontweight='bold', pad=20)

    # Legend
    # Create custom legend elements to match the style (square block next to text)
    handles = [
        patches.Patch(facecolor=colors['Smoke'], label='Smoke'),
        patches.Patch(facecolor=colors['Stress'], label='Stress'),
        patches.Patch(facecolor=colors['Soak'], label='Soak'),
        patches.Patch(facecolor=colors['Breakpoint'], label='Breakpoint'),
    ]
    ax.legend(handles=handles, loc='upper right', bbox_to_anchor=(0.7, 0.9), frameon=False, fontsize=10)

    # Grid and Spines
    ax.grid(axis='y', linestyle='-', alpha=0.2, color='lightgrey')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('lightgrey')
    ax.spines['bottom'].set_color('lightgrey')
    
    # Tick params
    ax.tick_params(axis='both', which='both', length=0)
    
    # Limits
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 11)

    plt.tight_layout()
    plt.savefig('load_test_types.png', dpi=300)
    print("Chart saved to load_test_types.png")

if __name__ == "__main__":
    generate_chart()
