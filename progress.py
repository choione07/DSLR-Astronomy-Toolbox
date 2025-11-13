import sys

def showProgress(current, total, description="Processing", bar_length=40):
    """
    Displays a block-style progress bar in the console.

    Args:
        current (int): The current iteration number (starting from 0).
        total (int): The total number of iterations.
        description (str): A short description of the task.
        bar_length (int): The character length of the progress bar.
    """
    # Handle the case where there are no items to process
    if total == 0:
        progress = 1.0
    else:
        progress = (current + 1) / total

    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + ' ' * (bar_length - filled_length)

    # Format the progress string
    progress_str = f"\r{description}: [{bar}] {current + 1}/{total} ({progress:.1%})"

    # Print to the console
    sys.stdout.write(progress_str)
    sys.stdout.flush()

    # Print a newline when the loop is complete
    if current + 1 == total or total == 0:
        sys.stdout.write('\n')