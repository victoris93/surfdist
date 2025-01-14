import numpy as np
import scipy.spatial
import nibabel as nib
from surfdist.load import load_cifti_labels,load_freesurfer_label,get_freesurfer_label, load_gifti_labels,load_FS_annot
import gdist

def surf_keep_cortex(surf, cortex):
    """
    Remove medial wall from cortical surface to ensure that shortest paths are only calculated through the cortex.
    Inputs
    -------
    surf : Tuple containing two numpy arrays of shape (n_nodes,3). Each node of the first array specifies the x, y, z
           coordinates one node of the surface mesh. Each node of the second array specifies the indices of the three
           nodes building one triangle of the surface mesh.
           (e.g. the output from nibabel.freesurfer.io.read_geometry)
    cortex : Array with indices of vertices included in within the cortex.
             (e.g. the output from nibabel.freesurfer.io.read_label)
    """

    # split surface into vertices and triangles
    vertices, triangles = surf

    # keep only the vertices within the cortex label
    cortex_vertices = np.array(vertices[cortex], dtype=np.float64)

    # keep only the triangles within the cortex label
    cortex_triangles = triangles_keep_cortex(triangles, cortex)

    return cortex_vertices, cortex_triangles
def triangles_keep_cortex(triangles, cortex):
    """
    Remove triangles with nodes not contained in the cortex label array
    This version iterates on the original allowing for users to use spun surfaces too
    """

    # for each face/triangle keep only those that only contain nodes within the list of cortex nodes
    input_shape = triangles.shape
    triangle_is_in_cortex = np.all(np.reshape(np.in1d(triangles.ravel(), cortex), input_shape), axis=1)

    cortex_triangles_old = np.array(triangles[triangle_is_in_cortex], dtype=np.int32)

    # Create a dictionary that maps the old node indices to the new ones
    index_mapping = {old_index: new_index for new_index, old_index in enumerate(cortex)}

    # Apply the mapping to the triangles
    cortex_triangles = np.vectorize(index_mapping.get)(cortex_triangles_old).astype(np.int32)

    return cortex_triangles

#### does not work on spun vertices as it requires monotonic increase which the spin destroys.
# def triangles_keep_cortex(triangles, cortex):
#     """
#     Remove triangles with nodes not contained in the cortex label array
#     """

#     # for or each face/triangle keep only those that only contain nodes within the list of cortex nodes
#     input_shape = triangles.shape
#     triangle_is_in_cortex = np.all(np.reshape(np.in1d(triangles.ravel(), cortex), input_shape), axis=1)

#     cortex_triangles_old = np.array(triangles[triangle_is_in_cortex], dtype=np.int32)

#     # reassign node index before outputting triangles
#     new_index = np.digitize(cortex_triangles_old.ravel(), cortex, right=True)
#     cortex_triangles = np.array(np.arange(len(cortex))[new_index].reshape(cortex_triangles_old.shape), dtype=np.int32)

#     return cortex_triangles

def translate_src(src, cortex):
    """
    Convert source nodes to new surface (without medial wall).
    """
    src_new = np.array(np.where(np.in1d(cortex, src))[0], dtype=np.int32)

    return src_new

def recort(input_data, surf, cortex):
    """
    Return data values to space of full cortex (including medial wall), with medial wall equal to zero.
    """
    data = np.zeros(len(surf[0]))
    data[cortex] = input_data
    return data

def find_node_match(simple_vertices, complex_vertices):
    """
    Thanks to juhuntenburg.
    Functions taken from https://github.com/juhuntenburg/brainsurfacescripts
    Finds those points on the complex mesh that correspond best to the
    simple mesh while forcing a one-to-one mapping.
    """


    # make array for writing in final voronoi seed indices
    voronoi_seed_idx = np.zeros((simple_vertices.shape[0],), dtype='int64')-1
    missing = np.where(voronoi_seed_idx == -1)[0].shape[0]
    mapping_single = np.zeros_like(voronoi_seed_idx)

    neighbours = 0
    col = 0

    while missing != 0:

        neighbours += 100
        # find nearest neighbours
        inaccuracy, mapping = scipy.spatial.KDTree(
            complex_vertices).query(simple_vertices, k=neighbours)
        # go through columns of nearest neighbours until unique mapping is
        # achieved, if not before end of neighbours, extend number of
        # neighbours
        while col < neighbours:
            # find all missing voronoi seed indices
            missing_idx = np.where(voronoi_seed_idx == -1)[0]
            missing = missing_idx.shape[0]
            if missing == 0:
                break
            else:
                # for missing entries fill in next neighbour
                mapping_single[missing_idx] = np.copy(
                    mapping[missing_idx, col])
                # find unique values in mapping_single
                unique, double_idx = np.unique(
                    mapping_single, return_inverse=True)
                # empty voronoi seed index
                voronoi_seed_idx = np.zeros(
                    (simple_vertices.shape[0],), dtype='int64')-1
                # fill voronoi seed idx with unique values
                for u in range(unique.shape[0]):
                    # find the indices of this value in mapping
                    entries = np.where(double_idx == u)[0]
                    # set the first entry to the value
                    voronoi_seed_idx[entries[0]] = unique[u]
                # go to next column
                col += 1

    return voronoi_seed_idx, inaccuracy

#### to do add input parser 
def AnatomyInputParser(data):
    """ Parses data input for anatomical surface data """
    if type(data)==tuple and len(data)==2:
        # print('using surface defined by tuple of vertices and faces')
        surf=data
    elif type(data)==str:
        if 'gii' in data:
            # print('using gifti anatomical surface')
            surf=(nib.load(data).darrays[0].data,nib.load(data).darrays[1].data)    
        else:
            # print('using freesurfer anatomical surface')
            surf=nib.freesurfer.read_geometry(data)
    return surf

def LabelInputParser(data,hemi,exceptions=[]):
    """ Parses data input for label surface data """
    if type(data)==str:
        if 'gii' in data:
            print('using gifti label data')
            labels= load_gifti_labels(data)
            medialWall = labels['???']
            del labels['???']
        elif '.dlabel.nii' in data:
            print('using cifti label file')
            labels= load_cifti_labels(data,hemi)
            medialWall = labels['???']
            del labels['???']
        elif '.annot' in data:
            print('using Freesurfer annotation')
            if len(exceptions)>0:
                labels=load_FS_annot(data)
                medialWall=labels[exceptions[0]]
            else:
                labels=load_FS_annot(data)
                medialWall=[]
    return labels,medialWall


import networkx as nx

def create_networkx_graph(vertices, faces):
    """ creates a networkX graph representaiton of a cortical surface"""
    G = nx.Graph()

    for face in faces:
        v1, v2, v3 = face
        G.add_edge(v1, v2)
        G.add_edge(v2, v3)
        G.add_edge(v1, v3)

    return G

#### to do 
### add the case where a user is adding data directly with a list of lists 


    # elif len(data)==3:
    #     print('data consists of a list of labels and node IDs, and a list of vertices included in the cortex')
