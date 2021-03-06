#!/usr/bin/env python


'''
This file contains strategy functions for running adaptivemd simulations
and project initializing function 'init_project'.

'''


from __future__ import print_function
import time

import os

import sampling_interface



class counter(object):
    def __init__(self, maxcount=0):
        self.n = maxcount
        self.i = 0

    @property
    def done(self):
        print("I am done: ", not self.i < self.n)
        return not self.i < self.n

    def increment(self):
        self.i += 1
        print("Incrementing counter to: ", self.i)


def print_project_work(project):
    print(project.name, "Project models\n - Number: {n_model}\n"
          .format(n_model=len(project.models)))

    print(project.name, "Project trajectories\n - Number: {n_traj}\n - Lengths:\n{lengths}\n"
          .format(n_traj=len(project.trajectories),
                  lengths=[t.length for t in project.trajectories]))



def print_last_model(project):

    try:
        mdat = project.models.last.data
        print(project.name, "Hopefully model prints below!")
        print(project.name, "Model created using modeller:",
              project.models.last.name)

        print(project.name, "attempted n_microstates: ",
              mdat['clustering']['k'])

        print(project.name, "length of cluster populations row: ",
              len(mdat['msm']['C'][0]))

        print(project.name, mdat['msm'])
        print(project.name, mdat['msm']['P'])
        print(project.name, mdat['msm']['C'])

    except:
        print(project.name, "tried to print model")
        pass


def randlength(n, incr, length, lengthvariance=0.2):

    import random

    rand = [random.random()*lengthvariance*2-lengthvariance
            for _ in range(n)]

    return [int(length*(1+r)/incr)*incr
            for r in rand]



def check_trajectory_minlength(project, minlength, n_steps=None,
                            n_run=None, trajectories=None,
                            environment=None, activate_prefix=None):

    if not trajectories:
        trajectories = project.trajectories

    tasks = list()
    for t in trajectories:

        tlength = t.length
        xlength = 0

        if n_steps:
            if tlength % n_steps > n_steps / 2:
                tlength += n_steps - tlength % n_steps

        if tlength < minlength:
            if n_steps:
                xlength += n_steps
            else:
                xlength += minlength - tlength

        if xlength > n_steps / 2:
            tasks.append(t.extend(xlength))
            if environment:
                tasks[-1].add_conda_env(
                    environment, activate_prefix)

    if n_run is not None and len(tasks) > n_run:
        tasks = tasks[:n_run]

    return tasks



def model_task(project, modeller, margs,
               trajectories=None, environment=None,
               activate_prefix=None):

    # model task goes last to ensure (on first one) that the
    # previous round of trajectories is done
    #print(project.name, "Using these in the model:\n", list(project.trajectories))
    if trajectories is None:
        trajectories = project.trajectories

    mtask = modeller.execute(list(trajectories), **margs)
    if environment:
        mtask.add_conda_env(environment, activate_prefix)

    project.queue(mtask)

    print(project.name, "Queued Modelling Task")
    print(project.name, "Using these modeller arguments:\n",margs)

    return mtask



#################################################################
#                                                               #
#   README for strategy_function                                #
#                                                               #
# This Function produces a workflow via dynamically generated   #
# workloads. Each workload is a set of tasks, some trajectory   #
# and possibly an analysis task.                                #
#                                                               #
# It is not robust and may not work if the arguments are not    #
# 'internally consistent' or violate some expeectation of this  #
# function.                                                     #
#                                                               #
#################################################################
def strategy_function(project, engine, n_run, n_ext, n_steps,
                      sampling_phase='xplor_microstates',
                      modeller=None, fixedlength=True,
                      longest=5000, continuing=True, minlength=None,
                      activate_prefix=None, environment=None,
                      read_margs=True, n_rounds=0, **kwargs):

    # TODO once making sure this works
    #      move it down to import when used
    #      after first round of tasks 
    sampling_function = sampling_interface.get_one(sampling_phase)

    c = counter(n_rounds)

    if n_rounds:
        assert(n_rounds > 0)
        print(project.name, "Going to do n_rounds:  ", c.n)

    # PREPARATION - Preprocess task setups
    print(project.name, "Using MD Engine: ", engine, engine.name)#, project.generators[engine.name].__dict__)
    print(project.name, "Using fixed length? ", fixedlength)

    lengthvariance=0.2

    if fixedlength:
        randbreak = [n_steps]*n_run

    else:
        randbreak = randlength(n_run, longest, n_steps, lengthvariance)

    if minlength is None:
        minlength = n_steps

    print_project_work(project)

    # ROUND 1 - No pre-existing data
    #         - will skip if revisiting project
    if len(project.trajectories) == 0:

        notfirsttime = False
        tasks = list()

        [tasks.append(project.new_trajectory(
         engine['pdb_file'], rb, engine).run())
         for rb in randbreak]

        if environment:
            [ta.add_conda_env(environment, activate_prefix) for ta in tasks]

        if not n_rounds or not c.done:
            project.queue(tasks)
            c.increment()

        print(project.name, "Number of tasks: ", len(tasks))
        print(project.name, "Queued First Tasks")
        print(project.name, "Trajectory lengths were: {0}"
              .format(', '.join([str(rb) for rb in randbreak])))

        yield lambda: any([ta.is_done() for ta in tasks])

        print(project.name, "First Tasks are done")

    else:
        notfirsttime = True


    print(project.name, "Starting Trajectory Extensions")

    def model_extend(modeller, randbreak, mtask=None, c=None):

        #print(project.name, "c_ext is ", c_ext, "({0})".format(n_ext))
        #print(project.name, "length of extended is: ", len(extended))

        # FIRST workload including a model this execution
        if c_ext == 0:
            if len(tasks) == 0:
                if not randbreak and not fixedlength:
                    randbreak += randlength(n_run, longest, n_steps)
                    lengtharg = randbreak

                else:
                    # this may already be set if new project
                    # was created in this run of adaptivemd
                    #locals()['randbreak'] = [n_steps]*n_run
                    lengtharg = n_steps

                trajectories = sampling_function(project, engine, lengtharg, n_run)
                #trajectories = project.new_ml_trajectory(engine, lengtharg, n_run, randomly)

                # Since first could use the initial PDB for next round
                # but will be heavy operation on single file 
                #trajectories = project.new_trajectory(engine['pdb_file'],
                #                                      engine, n_steps, n_run-1)

                #print(project.name, trajectories)
                if not n_rounds or not c.done:
                    [tasks.append(t.run()) for t in trajectories]
                    if environment:
                        [ta.add_conda_env(environment, activate_prefix) for ta in tasks]

                    for task in tasks:
                        project.queue(task)
                        time.sleep(0.1)

                    c.increment()

                # wait for all initial trajs to finish
                waiting = True
                while waiting:
                    # OK condition because we're in first
                    #    extension, as long as its a fresh
                    #    project.
                    if notfirsttime or len(project.trajectories) >= n_run:
                        print(project.name, "adding first/next modeller task")
                        mtask = model_task(project, modeller, margs, environment=environment, activate_prefix=activate_prefix)
                        tasks.append(mtask)
                        waiting = False
                    else:
                        time.sleep(3)

            #print(project.name, tasks)
            #print(project.name, "First Extensions' status':\n", [ta.state for ta in tasks])
            return any([ta.is_done() for ta in tasks[:-1]])

        # LAST workload in this execution
        elif c_ext == n_ext:
            if len(tasks) < n_run and mtask.is_done():
                # breaking convention of mtask last
                # is OK because not looking for mtask
                # after last round, only task.done
                if continuing:
                    mtask = model_task(project, modeller, margs, environment=environment, activate_prefix=activate_prefix)
                    tasks.append(mtask)

                print(project.name, "Queueing final extensions after modelling done")
                print(project.name, "Randbreak: \n", randbreak)
                unrandbreak = [2*n_steps - rb for rb in randbreak]
                unrandbreak.sort()
                unrandbreak.reverse()
                print(project.name, "Unrandbreak: \n", unrandbreak)

                trajectories = sampling_function(project, engine, unrandbreak, n_run)
                #trajectories = project.new_ml_trajectory(engine, unrandbreak, n_run, randomly)

                #print(project.name, trajectories)
                [tasks.append(t.run()) for t in trajectories]
                if environment:
                    [ta.add_conda_env(environment, activate_prefix) for ta in tasks]

                if not n_rounds or not c.done:
                    c.increment()
                    project.queue(tasks)

            return any([ta.is_done() for ta in tasks])

        else:
            # MODEL TASK MAY NOT BE CREATED
            #  - timing is different
            #  - just running trajectories until
            #    prior model finishes, then starting
            #    round of modelled trajs along
            #    with mtask
            if len(tasks) == 0:
                print(project.name, "Queueing new round of modelled trajectories")
                trajectories = sampling_function(project, engine, n_steps, n_run)
                #trajectories = project.new_ml_trajectory(engine, n_steps, n_run, randomly)

                if not n_rounds or not c.done:
                    c.increment()
                    [tasks.append(t.run()) for t in trajectories]
                    if environment:
                        [ta.add_conda_env(environment, activate_prefix) for ta in tasks]

                    project.queue(tasks)

                if mtask.is_done():
                    mtask = model_task(project, modeller, margs, environment=environment, activate_prefix=activate_prefix)
                    tasks.append(mtask)

                    return any([ta.is_done() for ta in tasks[:-1]])


                else:
                    return any([ta.is_done() for ta in tasks])

            else:
                #print(project.name, "not restarting with existing tasks")
                return any([ta.is_done() for ta in tasks])

    c_ext = 0
    mtask = None
    frac_ext_final_margs = 0.75

    if not read_margs:
        print(project.name, "THIS LINE SHOULD NOT PRINT!!")
        # start_margs = dict(tica_stride=4, tica_lag=50, tica_dim=4,
        #     clust_stride=1, msm_states=100, msm_lag=50)

        # final_margs = dict(tica_stride=4, tica_lag=50, tica_dim=6,
        #     clust_stride=2, msm_states=400, msm_lag=25)
    else:
        # We are just sneakily using a function without importing it
        # by using where it already is attached in the project...
        # ...it parses the AdaptiveMD configuration file format
        _margs = project.configurations.one.parse_configurations_file('margs.cfg')
        _key = project.name if project.name in _margs.keys() else 'all'

        start_margs = dict([ (k, int(v)) for k,v in _margs[_key].items() ])

        # TODO upgrade handling of margs...
        final_margs = start_margs

    def update_margs():
        margs=dict()
        progress = c_ext/float(n_ext)

        if c_ext == 1:
            progress_margs = 0
        elif progress < frac_ext_final_margs:
            progress_margs = progress/frac_ext_final_margs
        else:
            progress_margs = 1

        for key,baseval in start_margs.items():
            if key in final_margs:
                finalval = final_margs[key]
                val = int( progress_margs*(finalval-baseval) + baseval )
            else:
                val = baseval

            margs.update({key: val})

        return margs

    mtime = 0
    mtimes = list()
    # these will be redefined (repeatedly) in the control loop
    # need to declare the task lists now incase some of the
    # the control structure is skipped.
    tasks = list()
    xtasks = list()
    # Start of CONTROL LOOP
    # when on final c_ext ( == n_ext), will
    # grow trajs to minlength before
    # strategy terminates
    while c_ext <= n_ext and (not n_rounds or not c.done):

        print(project.name, "\n\n-------------------------------\nChecking Extension Lengths")

        done = False
        lastcheck = True
        priorext = 0
        # TODO fix, this isn't a consistent name "trajectories"
        trajectories = set()
        while not done and ( not n_rounds or not c.done ):

            print_project_work(project)

            print(project.name, "looking for too-short trajectories")

            if c.done:
                xtasks = list()
            else:
                xtasks = check_trajectory_minlength(project, minlength,
                             n_steps, n_run, environment=environment,
                             activate_prefix=activate_prefix)

            tnames = set()
            if len(trajectories) > 0:
                [tnames.add(_) for _ in set(zip(*trajectories)[0])]

            for xta in xtasks:
                tname = xta.trajectory.basename

                if tname not in tnames:
                    tnames.add(tname)
                    trajectories.add( (tname, xta) )
                    project.queue(xta)

            removals = list()
            for tname, xta in trajectories:
                if xta.state in {"fail","halted","success","cancelled"}:
                    removals.append( (tname, xta) )

            for removal in removals:
                trajectories.remove(removal)

            if len(trajectories) == n_run:

                # note this won't work with variable length
                # trajectories, ie randlength=True
                if all(map(lambda x: x[1].trajectory.length == minlength, trajectories)):
                    
                    if 'admd_titan_job.long.pbs' in os.listdir(os.getcwd()):
                        os.system("touch longjob")


                if priorext < n_run:
                    print(project.name, "Have full width of extensions")
                    c.increment()


            # setting this to look at next round
            priorext = len(trajectories)
            print(project.name, "XTRAJ LENGTHS ({0}, {1}):".format(priorext, n_run))
            [print(x[1].trajectory.length) for x in trajectories]

            if len(trajectories) == 0:
                if lastcheck:
                    print(project.name, "Extensions last check")
                    lastcheck = False
                    time.sleep(15)

                else:
                    print(project.name, "Extensions are done")
                    done = True

            else:
                if not lastcheck:
                    lastcheck = True

                time.sleep(15)

        print(project.name, "\n----------- Extension #{0}".format(c_ext))

        # when c_ext == n_ext, we just wanted
        # to use check_trajectory_minlength above
        if c_ext < n_ext and not c.done:

            print_project_work(project)

            if modeller:
                margs = update_margs()

                print(project.name, "Extending project with modeller")
                tasks = list()

                if mtask is None:

                    mtime -= time.time()
                    yield lambda: model_extend(modeller, randbreak, c=c)

                    print(project.name, "Set a current modelling task")
                    mtask = tasks[-1]
                    print(project.name, "First model task is: ", mtask)

                # TODO don't assume mtask not None means it
                #      has is_done method. outer loop needs
                #      upgrade
                elif mtask.is_done():

                    mtime += time.time()
                    mtimes.append(mtime)
                    mtime = -time.time()
                    print(project.name, "Current modelling task is done")
                    print(project.name, "It took {0} seconds".format(mtimes[-1]))
                    c_ext += 1

                    yield lambda: model_extend(modeller, randbreak, mtask, c=c)

                    print_last_model(project)
                    mtask = tasks[-1]
                    print(project.name, "Set a new current modelling task")

                elif not mtask.is_done():
                    print(project.name, "Continuing trajectory tasks, waiting on model")
                    yield lambda: model_extend(modeller, randbreak, mtask, c=c)

                else:
                    print(project.name, "Not sure how we got here")
                    pass

            # don't currently have a modeller-less workload function
            else:
                pass

        # End of CONTROL LOOP
        # need to increment c_ext to exit the loop
        else:
            c_ext += 1
            # This line forces a wait if we shot through above
            # loops to submit only 1 round of tasks, otherwise
            # the logic below can signal a shutdown if the
            # workers are a bit lagged compared to this loop.
            yield lambda: any([ta.is_done() for ta in tasks+xtasks])

    # we should not arrive here until the final round
    # of extensions are queued and at least one of them
    # is complete.
    def all_done():
        '''
        This function scavenges project for idle workers.
        They are shut down if idle to flush the output.
        Returns function that returns True when all workers
        have been shut down.
        '''         
        #print(project.name, "Checking if all done")
        idle_time = 20
        for w in project.workers:
            if w.state not in {'down','dead'}:
                try:
                    idx = list(zip(*workers))[0].index(w)
                    if not w.n_tasks:
                        if time.time() - workers[idx][1] > idle_time:
                            w.execute('shutdown')
                    else:
                        workers.pop(idx)

                except (ValueError, IndexError):
                    if not w.n_tasks:
                        workers.append((w, time.time()))

        #print([w.state for w,t in workers])
        return all([ w.state in {'down','dead'}
                     for w in project.workers
                  ])

    print(project.name, "Waiting for all done")
    workers = list()
    yield lambda: all_done()
    time.sleep(5)

    print(project.name, "Simulation Event Finished")



def init_project(p_name, sys_name=None, m_freq=None, p_freq=None,
                 platform=None, dbhost=None, w_threads=None):
#def init_project(p_name, **freq):

    from adaptivemd import Project

    #if p_name in Project.list(): 
    #    print(project.name, "Deleting existing version of this test project") 
    #    Project.delete(p_name)

    if dbhost is not None:
        Project.set_dbhost(dbhost)

    project = Project(p_name)

    if project.name in Project.list():
        print(project.name, "Project {0} exists, reading it from database"
              .format(project.name))

    else:

        from adaptivemd import File, OpenMMEngine
        from adaptivemd.analysis.pyemma import PyEMMAAnalysis

        #####################################
        # NEW initialize sequence
        configuration_file = 'configuration.cfg'
        project.initialize(configuration_file)
        #
        # OLD initialize sequence
        #from adaptivemd import LocalResource
        #resource = LocalResource('/lustre/atlas/scratch/jrossyra/bip149/admd/')
        #project.initialize(resource)
        #####################################

        f_name = '{0}.pdb'.format(sys_name)

        # only works if filestructure is preserved as described in 'jro_ntl9.ipynb'
        # and something akin to job script in 'admd_workers.pbs' is used
        f_base = 'file:///$ADAPTIVEMD/examples/files/{0}/'.format(sys_name)

        f_structure = File(f_base + f_name).load()

        f_system_2 = File(f_base + 'system-2.xml').load()
        f_integrator_2 = File(f_base + 'integrator-2.xml').load()

        f_system_5 = File(f_base + 'system-5.xml').load()
        f_integrator_5 = File(f_base + 'integrator-5.xml').load()

        sim_args = '-r -p {0}'.format(platform)

        if platform == 'CPU':
            print(project.name, "Using CPU simulation platform with {0} threads per worker"
                  .format(w_threads))

            sim_args += ' --cpu-cpu-threads {0}'.format(w_threads)

        engine_2 = OpenMMEngine(f_system_2, f_integrator_2,
                              f_structure, sim_args).named('openmm-2')

        engine_5 = OpenMMEngine(f_system_5, f_integrator_5,
                              f_structure, sim_args).named('openmm-5')

        m_freq_2 = m_freq
        p_freq_2 = p_freq
        m_freq_5 = m_freq * 2 / 5
        p_freq_5 = p_freq * 2 / 5

        engine_2.add_output_type('master', 'allatoms.dcd', stride=m_freq_2)
        engine_2.add_output_type('protein', 'protein.dcd', stride=p_freq_2,
                               selection='protein')

        engine_5.add_output_type('master', 'allatoms.dcd', stride=m_freq_5)
        engine_5.add_output_type('protein', 'protein.dcd', stride=p_freq_5,
                               selection='protein')

        ca_features = {'add_distances_ca': None}
        #features = {'add_inverse_distances': {'select_Backbone': None}}
        ca_modeller_2 = PyEMMAAnalysis(engine_2, 'protein', ca_features
                                 ).named('pyemma-ca-2')

        ca_modeller_5 = PyEMMAAnalysis(engine_5, 'protein', ca_features
                                 ).named('pyemma-ca-5')

        pos = ['(rescode K and mass > 13) ' +
               'or (rescode R and mass > 13) ' + 
               'or (rescode H and mass > 13)']
        neg = ['(rescode D and mass > 13) ' +
               'or (rescode E and mass > 13)']

        ionic_features = {'add_distances': {'select': pos},
                          'kwargs': {'indices2': {'select': neg}}}

        all_features = [ca_features, ionic_features]

        #ok#ionic_modeller = {'add_distances': {'select':
        #ok#                                   ['rescode K or rescode R or rescode H']},
        #ok#                  'kwargs': {'indices2': {'select':
        #ok#                                   'rescode D or rescode E']}}}
        #contact_features = [ {'add_inverse_distances':
        #                         {'select_Backbone': None}},
        #                     {'add_residue_mindist': None,
        #                      'kwargs': {'threshold': 0.6}}
        #                   ]

        all_modeller_2 = PyEMMAAnalysis(engine_2, 'protein', all_features
                                 ).named('pyemma-ionic-2')

        all_modeller_5 = PyEMMAAnalysis(engine_5, 'protein', all_features
                                 ).named('pyemma-ionic-5')

        project.generators.add(ca_modeller_2)
        project.generators.add(all_modeller_2)
        project.generators.add(ca_modeller_5)
        project.generators.add(all_modeller_5)
        project.generators.add(engine_2)
        project.generators.add(engine_5)

        [print(g) for g in project.generators]


    return project

