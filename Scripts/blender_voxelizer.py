'''
Paste this script into your blender file's scripting tab as a new file and run it. A "Voxelizer" tab should appear on the right of the 3D Viewport. If it is hidden, press the 'N' key while having the mouse inside the 3D Viewport. 
The voxelization process will freeze blender, so it is recommended to open the console from the "Window" menu to check on progress.
'''


bl_info = {
    "name": "Animation Voxelizer",
    "blender": (2, 91, 2),
    "category": "Object",
}

import bpy
import bmesh
import numpy as np
import os

from mathutils import Vector
from math import floor

BLOCK_SIZE = 1 # How many blender units equivelate to 1 Minecraft block (higher values reduce size of structure in the game)

def create_texture_cache(objects, cache):
    print("[Voxelizer] Creating texture cache")
    cache = {}
    for obj in objects:
        for material_slot in obj.material_slots:
            material = material_slot.material
            if not material.name in cache:
                for x in material.node_tree.nodes:
                    if x.type=='TEX_IMAGE':
                        image_texture = x.image
                        print("[Voxelizer] Using image "+image_texture.name+ " for material "+material.name)
                        cache[material.name] = image_texture
                        break
    print("[Voxelizer] Texture cache done")


def create_blocks(obj, origin=Vector((0,0,0)), use_nodes=False,block_scale=1.0,material_textures={}):
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    
    blocks = {}
    
    # Extract vertex colors if present
    vertex_colors = [(1.0,1.0,1.0)] * len(bm.verts)
    if use_nodes:
        uv_layer = bm.loops.layers.uv.active
        
        for face in bm.faces:
            found_texture = False
            material = obj.material_slots[face.material_index].material
            if material.name in material_textures:
                image_texture = material_textures[material.name]
                found_texture= True
            
            for loop in face.loops:
                if found_texture:
                    uv = loop[uv_layer].uv
                    
                    pixel_x = int((uv.x % 1) * image_texture.size[0])
                    pixel_y = int((uv.y % 1) * image_texture.size[1])
                    
                    pixel_index = (pixel_y * image_texture.size[0] + pixel_x) * image_texture.channels
                    
                    vertex_colors[loop.vert.index] = Vector(image_texture.pixels[pixel_index:pixel_index+3])
                else:
                    vertex_colors[loop.vert.index] = [1,1,1]
            
    elif 'Col' in bm.loops.layers.color:
        color_layer = bm.loops.layers.color['Col']
        for face in bm.faces:
            for loop in face.loops:
                vertex_colors[loop.vert.index] = loop[color_layer]
    
    for vertex in bm.verts:
        vertex_pos = obj.matrix_world @ vertex.co
        block_pos = (vertex_pos - origin) / block_scale
        block_x = floor(block_pos.x)
        block_y = floor(block_pos.y)
        block_z = floor(block_pos.z)
        
        vertex_color = vertex_colors[vertex.index]
        if (block_x,block_y,block_z) not in blocks or vertex_color[0] < blocks[(block_x,block_y,block_z)][0]:
            # vertex_color = (max(0,min(1.0, block_z/30)), max(0,min(1.0, block_z/100)), 0.0) # This was used to make a gradient based on height
            blocks[block_x,block_y,block_z] = (floor(vertex_color[0]*255),floor(vertex_color[1]*255),floor(vertex_color[2]*255))
                    
    bm.free()
    return blocks

def save_blocks(blocks, filename):
    with open(filename, 'w') as f:
        for block_pos in blocks:
            block_color = blocks[block_pos]
            f.write(f'{block_pos[0]},{block_pos[2]},{-block_pos[1]},{block_color[0]},{block_color[1]},{block_color[2]};') # Swap Y and Z for compatibility with Minecraft and take the opposite of Y to correct mirroring
      
class VOXELIZER_PT_panel(bpy.types.Panel):
    bl_idname = "VOXELIZER_PT_panel"      # Unique identifier for buttons and menu items to reference.
    bl_label = "Voxelizer"             
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Voxelizer"

    def draw(self, context):
        col1 = self.layout.column(align = True)
        col1.prop(context.scene, "vx_output_dir_prop")
        col1.prop(context.scene, "vx_use_nodes")
        col1.prop(context.scene,"vx_selected_only")
        
        col2 = self.layout.column(align = True)
        col2.prop(context.scene, "vx_start_frame_prop")
        col2.prop(context.scene, "vx_end_frame_prop")
        col2.prop(context.scene,"vx_block_scale")
        self.layout.operator("object.voxelize", icon='MESH_CUBE', text="Voxelize")

class Voxelizer_OT_operator(bpy.types.Operator):
    bl_idname = 'object.voxelize'
    bl_label = 'Voxelize'
    bl_options = {"REGISTER"}
    
    def execute(self, context):        # execute() is called when running the operator.
        global depsgraph, obj, block_size, image_texture
        
        output_dir = bpy.context.scene.vx_output_dir_prop
        
        if output_dir.startswith('//'):
            self.report({"ERROR"}, "Output dir: Relative paths are not supported.")
            return {"CANCELLED"}
        elif not os.path.exists(output_dir):
            self.report({"ERROR"}, "Output dir does not exist.")
            return {"CANCELLED"}
        
        
        depsgraph = context.evaluated_depsgraph_get()
        
        if len(context.selected_objects) < 1:
            self.report({"ERROR"}, "No object selected.")
            return {"CANCELLED"}
        
        try:
            bpy.ops.wm.save_mainfile() # In case something goes wrong
        except:
            print("[Voxelizer] Failed to save file")

        if bpy.context.scene.vx_use_nodes is not None:
            print("Using image texture for colors")
        else:
            print("Using vertex colors")

        objects = []
        if bpy.context.scene.vx_selected_only:
            objects = context.selected_objects
        else:
            objects = meshes = set(o for o in bpy.context.scene.objects if o.type == 'MESH')


        cache={}
        if bpy.context.scene.vx_use_nodes:
            create_texture_cache(objects,cache)

        for frame in range(bpy.context.scene.vx_start_frame_prop, bpy.context.scene.vx_end_frame_prop+1):
            bpy.context.scene.frame_set(frame)
            blocks = {}
            for obj in objects:
                blocks.update(create_blocks(obj,use_nodes=bpy.context.scene.vx_use_nodes,block_scale=bpy.context.scene.vx_block_scale,material_textures=cache))
            save_blocks(blocks, os.path.join(output_dir,f'{frame}.blocks'))
            print("[Voxelizer] Saved frame "+str(frame))
            
            
        blocks = None
        return {"FINISHED"}


def register():
    bpy.types.Scene.vx_output_dir_prop = bpy.props.StringProperty(name = "Output directory", description = "Where the voxel data for every frame should be saved to", default = "", subtype = "DIR_PATH")
    bpy.types.Scene.vx_use_nodes = bpy.props.BoolProperty(name = "Use Images from Nodes", description = "Wheter or not the script should read the textures from material nodes. Disable to use vertex colors instead", default = False)
    bpy.types.Scene.vx_selected_only = bpy.props.BoolProperty(name = "Selected Only", description = "Only voxelize selected meshes", default = False)
    bpy.types.Scene.vx_start_frame_prop = bpy.props.IntProperty(name = "Start frame", default = 0)
    bpy.types.Scene.vx_end_frame_prop = bpy.props.IntProperty(name = "End frame", default = 250)
    bpy.types.Scene.vx_block_scale = bpy.props.FloatProperty(name="Block scale",description="Ratio of blender units to minecraft blocks",default=1.0)
    
    bpy.utils.register_class(Voxelizer_OT_operator)
    bpy.utils.register_class(VOXELIZER_PT_panel)

def unregister():
    bpy.utils.unregister_class(VOXELIZER_PT_panel)
    bpy.utils.unregister_class(Voxelizer_OT_operator)
    
    del bpy.types.Scene.vx_output_dir_prop
    del bpy.types.Scene.vx_use_nodes
    del bpy.types.Scene.vx_start_frame_prop
    del bpy.types.Scene.vx_end_frame_prop


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()