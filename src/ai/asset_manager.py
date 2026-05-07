import tkinter as tk
from tkinter import ttk, messagebox
import os
from datetime import datetime
import json
from pathlib import Path

class AIAssetManager:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Asset Filename Manager")
        
        # Load configuration
        self.config = self.load_config()
        
        # State variables
        self.current_project = tk.StringVar(value=self.config.get('last_project', ''))
        self.current_sequence = tk.StringVar()
        self.current_shot = tk.StringVar(value="0100")
        self.current_type = tk.StringVar(value="txt2img")
        self.current_vendor = tk.StringVar(value="cd")  # cd for ComfyUI
        self.current_version = tk.IntVar(value=1)
        
        # Create main frames
        self.create_frames()
        self.create_project_controls()
        self.create_filename_controls()
        self.create_comfy_controls()
        self.create_output_display()
        
        # Initialize the preview
        self.update_preview()

    def load_config(self):
        config_path = Path.home() / '.ai_asset_manager_config.json'
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        return {
            'projects': {},
            'last_project': '',
            'vendor_codes': {
                'ComfyUI': 'cd',
                'Stable Diffusion': 'sd',
                'Midjourney': 'mj',
                'DALL-E': 'dl'
            }
        }

    def save_config(self):
        config_path = Path.home() / '.ai_asset_manager_config.json'
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def create_frames(self):
        # Main container with padding
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Left frame for inputs
        self.left_frame = ttk.Frame(self.main_frame)
        self.left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # Right frame for outputs
        self.right_frame = ttk.Frame(self.main_frame)
        self.right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))

    def create_project_controls(self):
        # Project Section
        project_frame = ttk.LabelFrame(self.left_frame, text="Project Settings", padding="5")
        project_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(project_frame, text="Project:").grid(row=0, column=0, sticky=tk.W)
        self.project_entry = ttk.Entry(project_frame, textvariable=self.current_project)
        self.project_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        ttk.Label(project_frame, text="Sequence:").grid(row=1, column=0, sticky=tk.W)
        self.sequence_entry = ttk.Entry(project_frame, textvariable=self.current_sequence)
        self.sequence_entry.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        ttk.Label(project_frame, text="Shot:").grid(row=2, column=0, sticky=tk.W)
        self.shot_entry = ttk.Entry(project_frame, textvariable=self.current_shot)
        self.shot_entry.grid(row=2, column=1, sticky=(tk.W, tk.E))

        # Bind updates
        for entry in [self.project_entry, self.sequence_entry, self.shot_entry]:
            entry.bind('<KeyRelease>', lambda e: self.update_preview())

    def create_filename_controls(self):
        # Filename Section
        filename_frame = ttk.LabelFrame(self.left_frame, text="Filename Settings", padding="5")
        filename_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Type dropdown
        ttk.Label(filename_frame, text="Type:").grid(row=0, column=0, sticky=tk.W)
        types = ['txt2img', 'img2img', 'inpaint', 'upscl', 'txt2vid', 'vid2vid']
        self.type_combo = ttk.Combobox(filename_frame, textvariable=self.current_type, values=types)
        self.type_combo.grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        # Version spinbox
        ttk.Label(filename_frame, text="Version:").grid(row=1, column=0, sticky=tk.W)
        self.version_spin = ttk.Spinbox(filename_frame, from_=1, to=999, textvariable=self.current_version)
        self.version_spin.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        # Bind updates
        self.type_combo.bind('<<ComboboxSelected>>', lambda e: self.update_preview())
        self.version_spin.bind('<KeyRelease>', lambda e: self.update_preview())

    def create_comfy_controls(self):
        # ComfyUI Section
        comfy_frame = ttk.LabelFrame(self.left_frame, text="ComfyUI Settings", padding="5")
        comfy_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # ComfyUI node references
        ttk.Label(comfy_frame, text="Model:").grid(row=0, column=0, sticky=tk.W)
        self.model_entry = ttk.Entry(comfy_frame)
        self.model_entry.insert(0, "%model.name%")
        self.model_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        ttk.Label(comfy_frame, text="Sampler:").grid(row=1, column=0, sticky=tk.W)
        self.sampler_entry = ttk.Entry(comfy_frame)
        self.sampler_entry.insert(0, "%sampler.name%")
        self.sampler_entry.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        # Add button
        self.create_button = ttk.Button(comfy_frame, text="Create Structure", command=self.create_folder_structure)
        self.create_button.grid(row=2, column=0, columnspan=2, pady=5)

    def create_output_display(self):
        # Output Section
        output_frame = ttk.LabelFrame(self.right_frame, text="Generated Names", padding="5")
        output_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Preview
        self.preview_text = tk.Text(output_frame, height=20, width=60)
        self.preview_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self.preview_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.preview_text.configure(yscrollcommand=scrollbar.set)

    def update_preview(self):
        # Clear preview
        self.preview_text.delete(1.0, tk.END)
        
        # Generate base filename
        base = self.generate_base_filename()
        
        # Add preview text
        self.preview_text.insert(tk.END, "VFX Standard Filename:\n")
        self.preview_text.insert(tk.END, f"{base}.png\n\n")
        
        # Add ComfyUI variants
        self.preview_text.insert(tk.END, "ComfyUI Variants:\n")
        self.preview_text.insert(tk.END, f"{base}_{self.model_entry.get()}_{self.sampler_entry.get()}.png\n")
        self.preview_text.insert(tk.END, f"{base}_{self.model_entry.get()}_{self.sampler_entry.get()}-0001.png\n")
        
        # Add folder structure preview
        self.preview_text.insert(tk.END, "\nFolder Structure:\n")
        self.preview_text.insert(tk.END, self.generate_folder_structure_preview())

    def generate_base_filename(self):
        project = self.current_project.get()
        sequence = self.current_sequence.get()
        shot = self.current_shot.get().zfill(4)
        type_code = self.current_type.get()
        vendor = self.current_vendor.get()
        version = f"v{str(self.current_version.get()).zfill(3)}"
        
        return f"{project}_{sequence}_{shot}_{type_code}_{vendor}_{version}"

    def generate_folder_structure_preview(self):
        project = self.current_project.get()
        sequence = self.current_sequence.get()
        shot = self.current_shot.get().zfill(4)
        
        structure = f"{project}/\n"
        structure += f"  └─ {sequence}/\n"
        structure += f"      └─ {shot}/\n"
        structure += "          ├─ concept/\n"
        structure += "          │   └─ _prompts.txt\n"
        structure += "          ├─ iterations/\n"
        structure += "          │   └─ settings.txt\n"
        structure += "          └─ finals/\n"
        
        return structure

    def create_folder_structure(self):
        if not self.current_project.get() or not self.current_sequence.get():
            messagebox.showerror("Error", "Project and Sequence are required!")
            return
            
        base_path = Path(self.current_project.get())
        sequence_path = base_path / self.current_sequence.get()
        shot_path = sequence_path / self.current_shot.get().zfill(4)
        
        # Create directories
        for subdir in ['concept', 'iterations', 'finals']:
            (shot_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # Create _prompts.txt
        prompts_file = shot_path / 'concept' / '_prompts.txt'
        if not prompts_file.exists():
            with open(prompts_file, 'w') as f:
                f.write(f"# Prompts for {self.current_shot.get()}\n")
                f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Create settings.txt
        settings_file = shot_path / 'iterations' / 'settings.txt'
        if not settings_file.exists():
            with open(settings_file, 'w') as f:
                f.write(f"# Generation Settings for {self.current_shot.get()}\n")
                f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("Model: %model.name%\n")
                f.write("Sampler: %sampler.name%\n")
                f.write("Steps: %steps.value%\n")
                f.write("CFG: %cfg.value%\n")
                f.write("Seed: %seed.value%\n")
        
        messagebox.showinfo("Success", "Folder structure created successfully!")

def main():
    root = tk.Tk()
    app = AIAssetManager(root)
    root.mainloop()

if __name__ == "__main__":
    main()