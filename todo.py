"""Simple command-line to-do list application.

Tasks are stored in a local JSON file so they persist across runs.
Only Python's standard library is used.
"""

import json
import os
import sys

# Path to the JSON file used for persistence. Stored next to this script.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo.json")


def load_tasks():
    """Load tasks from the JSON file. Return an empty list if the file
    does not exist or is unreadable/corrupt."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Validate that the loaded data is a list of dicts with the
            # expected keys; otherwise start fresh to avoid crashes later.
            if isinstance(data, list):
                return [
                    {"description": str(t.get("description", "")),
                     "completed": bool(t.get("completed", False))}
                    for t in data if isinstance(t, dict)
                ]
            return []
    except (json.JSONDecodeError, OSError):
        print("Warning: could not read existing data file. Starting fresh.")
        return []


def save_tasks(tasks):
    """Persist tasks to the JSON file."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
    except OSError as e:
        print(f"Error: could not save tasks ({e}).")


def list_tasks(tasks):
    """Print all tasks with a 1-based index and their status."""
    if not tasks:
        print("No tasks yet. Add one with the 'add' command.")
        return
    print("\nYour tasks:")
    for i, task in enumerate(tasks, start=1):
        status = "[x]" if task["completed"] else "[ ]"
        print(f"  {i}. {status} {task['description']}")
    print()


def add_task(tasks):
    """Prompt the user for a description and append a new task."""
    description = input("Enter the task description: ").strip()
    if not description:
        print("Task description cannot be empty.")
        return
    tasks.append({"description": description, "completed": False})
    save_tasks(tasks)
    print(f"Added: {description}")


def parse_index(raw, tasks):
    """Convert user input to a valid 0-based list index, or return None
    if the input is not a valid task number."""
    try:
        idx = int(raw) - 1  # Users see 1-based indices.
    except ValueError:
        print("Please enter a valid number.")
        return None
    if idx < 0 or idx >= len(tasks):
        print(f"No task with number {raw}. Use 'list' to see valid numbers.")
        return None
    return idx


def delete_task(tasks):
    """Remove a task selected by its displayed index."""
    if not tasks:
        print("Nothing to delete - your list is empty.")
        return
    raw = input("Enter the number of the task to delete: ").strip()
    idx = parse_index(raw, tasks)
    if idx is None:
        return
    removed = tasks.pop(idx)
    save_tasks(tasks)
    print(f"Deleted: {removed['description']}")


def complete_task(tasks):
    """Mark a task as completed."""
    if not tasks:
        print("No tasks to complete.")
        return
    raw = input("Enter the number of the task to mark complete: ").strip()
    idx = parse_index(raw, tasks)
    if idx is None:
        return
    if tasks[idx]["completed"]:
        print("That task is already completed.")
        return
    tasks[idx]["completed"] = True
    save_tasks(tasks)
    print(f"Completed: {tasks[idx]['description']}")


def print_help():
    """Show the available commands."""
    print(
        "\nCommands:\n"
        "  add      - Add a new task\n"
        "  list     - List all tasks\n"
        "  done     - Mark a task as completed\n"
        "  delete   - Delete a task\n"
        "  help     - Show this help message\n"
        "  quit     - Exit the program\n"
    )


def main():
    """Main interactive loop."""
    tasks = load_tasks()
    print("To-Do List - type 'help' to see commands.")

    # Map command names to the functions that handle them.
    actions = {
        "add": lambda: add_task(tasks),
        "list": lambda: list_tasks(tasks),
        "done": lambda: complete_task(tasks),
        "delete": lambda: delete_task(tasks),
        "help": print_help,
    }

    while True:
        try:
            command = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Exit cleanly on Ctrl-D / Ctrl-C.
            print()
            break

        if command in ("quit", "exit"):
            break
        if not command:
            continue

        action = actions.get(command)
        if action is None:
            print(f"Unknown command: {command!r}. Type 'help' for options.")
            continue
        action()

    print("Goodbye!")


if __name__ == "__main__":
    # sys is imported per the requirements; using it for a clean exit code.
    main()
    sys.exit(0)
