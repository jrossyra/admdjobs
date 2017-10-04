


import numpy as np



def get_model(project):
    models = sorted(project.models, reverse=True, key=lambda m: m.__time__)

    for model in models:
        #assert(isinstance(model, Model))
        data = model.data
        c = data['msm']['C']
        s =  np.sum(c, axis=1)
        if 0 not in s:
            q = 1.0 / s

            return data, c, q


def random_restart(project, number=1):
    trajlist = list()

    if len(project.trajectories) > 0:
        print("Using random vector to select new frames")
        [trajlist.append(project.trajectories.pick().pick()) for _ in range(number)]

    return trajlist


def xplor_microstates(project, number=1):
    '''
    This one is the same as project.new_ml_trajectory
    '''

    data, c, q = get_model(project)
    trajlist = list()

    # not a good method to get n_states
    # populated clusters in
    # data['msm']['C'] may be less than k
    #n_states = data['clustering']['k']
    n_states = len(c)

    modeller = data['input']['modeller']

    outtype = modeller.outtype

    # the stride of the analyzed trajectories
    used_stride = modeller.engine.types[outtype].stride

    # all stride for full trajectories
    full_strides = modeller.engine.full_strides

    frame_state_list = {n: [] for n in range(n_states)}
    for nn, dt in enumerate(data['clustering']['dtrajs']):
        for mm, state in enumerate(dt):
            # if there is a full traj with existing frame, use it
            if any([(mm * used_stride) % stride == 0 for stride in full_strides]):
                frame_state_list[state].append((nn, mm * used_stride))

    # remove states that do not have at least one frame
    for k in range(n_states):
        if len(frame_state_list[k]) == 0:
            q[k] = 0.0

    # and normalize the remaining ones
    q /= np.sum(q)

    state_picks = np.random.choice(np.arange(len(q)), size=number, p=q)

    print("Using probability vector for states q:\n", q)
    print("...we have chosen these states:\n", [(s, q[s]) for s in state_picks])

    filelist = data['input']['trajectories']

    picks = [
        frame_state_list[state][np.random.randint(0,
                len(frame_state_list[state]))]
        for state in state_picks
        ]

    [trajlist.append(filelist[pick[0]][pick[1]]) for pick in picks]

    print("Trajectory picks list:\n", trajlist)
    return trajlist


# TODO first time for any function won't find model
#      - need to invoke random sampling...
#        - try to automate...
def get_one(name_func):

    _sampling_function = globals()[name_func]
    print("Retrieved sampling function: ", _sampling_function)

    # Use Sampled Frames to make New Trajectories
    def sampling_function(project, engine, length, number, *args):

        if isinstance(length, int):
            assert(isinstance(number, int))
            length = [length] * number

        if isinstance(length, list):
            if number is None:
                number = len(length)

            trajectories = [

                project.new_trajectory(frame, length[i], engine)
                for i,frame in enumerate(

                    _sampling_function(project, number, *args))
            ]

            return trajectories


    return sampling_function

