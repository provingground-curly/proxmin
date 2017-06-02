from __future__ import print_function, division
import logging
import numpy as np
from functools import partial

from . import utils

logging.basicConfig()
logger = logging.getLogger("proxmin.algorithms")

def pgm(X0, prox_f, step_f, relax=1.49, e_rel=1e-6, max_iter=1000, traceback=False):
    """Proximal Gradient Method

    Adapted from Combettes 2009, Algorithm 3.4
    """
    X = X0.copy()
    Z = X0.copy()

    history = []
    for it in range(max_iter):

        # Optionally store the current state
        if traceback:
            history.append(X)

        _X = prox_f(Z, step_f)
        Z = X + relax*(_X - X)
        # test for fixed point convergence
        if utils.l2sq(X - _X) <= e_rel**2*utils.l2sq(X):
            X = _X
            break

        X = _X

    if it+1 == max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))

    if not traceback:
        return X
    else:
        tr = utils.Traceback(it=it, history=history)
        return X, tr


def apgm(X0, prox_f, step_f, e_rel=1e-6, max_iter=1000, traceback=False):
    """Accelerated Proximal Gradient Method

    Adapted from Combettes 2009, Algorithm 3.6
    """
    X = X0.copy()
    Z = X0.copy()
    t = 1.
    history = []
    for it in range(max_iter):

        # Optionally store the current state
        if traceback:
            history.append(X)

        _X = prox_f(Z, step_f)
        t_ = 0.5*(1 + np.sqrt(4*t*t + 1))
        gamma = 1 + (t - 1)/t_
        Z = X + gamma*(_X - X)
        # test for fixed point convergence
        if utils.l2sq(X - _X) <= e_rel**2*utils.l2sq(X):
            X = _X
            break

        t = t_
        X = _X

    if it+1 == max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))

    if not traceback:
        return X
    else:
        tr = utils.Traceback(it=it, history=history)
        return X, tr


def admm(X0, prox_f, step_f, prox_g, step_g, L=None, e_rel=1e-6, max_iter=1000, traceback=False):

    """Alternating Direction Method of Multipliers

    Adapted from Parikh and Boyd (2009).
    """

    # get/check compatible step size for g
    step_g = utils.get_step_g(step_f, L=L, step_g=step_g)
    # use matrix adaptor for convenient & fast notation
    L = utils.MatrixOrNone(L)

    # init
    X = X0.copy()
    Z = L.dot(X)
    U = np.zeros_like(Z)
    errors = []
    history = []

    for it in range(max_iter):

        # Optionally store the current state
        if traceback:
            history.append(X)

        # Update the variables
        X, Z_, U, LX = utils.update_variables(X, Z, U, prox_f, step_f, prox_g, step_g, L)
        # ADMM Convergence Criteria, adapted from Boyd 2011, Sec 3.3.1
        convergence, error = utils.check_constraint_convergence(step_f, step_g, X, LX, Z_, Z, U, L, e_rel)
        Z = Z_

        # Store the errors
        if traceback:
            errors.append(error)

        if convergence:
            break

    # undo matrix adaptor
    L = L.L

    if it+1 == max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))

    if not traceback:
        return X
    else:
        tr = utils.Traceback(it=it, Z=Z, U=U, errors=errors, history=history)
        return X, tr


def sdmm(X0, prox_f, step_f, proxs_g, steps_g, Ls=None, e_rel=1e-6, max_iter=1000, traceback=False):

    """Implement Simultaneous-Direction Method of Multipliers

    This implements the SDMM algorithm derived from Algorithm 7.9 from Combettes and Pesquet (2009),
    Section 4.4.2 in Parikh and Boyd (2013), and Eq. 2.2 in Andreani et al. (2007).

    In Combettes and Pesquet (2009) they use a matrix inverse to solve the problem.
    In our case that is the inverse of a sparse matrix, which is no longer sparse and too
    costly to implement.
    The `scipy.sparse.linalg` module does have a method to solve a sparse matrix equation,
    using Algorithm 7.9 directly still does not yield the correct result,
    as the treatment of penalties due to constraints are on equal footing with our likelihood
    proximal operator and require a significant change in the way we calculate step sizes to converge.

    Instead we calculate the constraint vectors (as in SDMM) but extend the update of the ``X`` matrix
    using a modified version of the ADMM X update function (from Parikh and Boyd, 2009),
    using an augmented Lagrangian for multiple linear constraints as given in Andreani et al. (2007).

    """
    if not hasattr(proxs_g, "__iter__"):
        proxs_g = [proxs_g]
    if not hasattr(steps_g, "__iter__"):
        steps_g = [steps_g]
    if not hasattr(Ls, "__iter__"):
        Ls = [Ls]
    M = len(proxs_g)
    assert len(steps_g) == M
    assert len(Ls) == M

    # get/check compatible step sizes for g
    # use matrix adaptor for convenient & fast notation
    for i in range(M):
        steps_g[i] = utils.get_step_g(step_f, L=Ls[i], step_g=steps_g[i])
        Ls[i] = utils.MatrixOrNone(Ls[i])

    # Initialization
    X = X0.copy()
    Z = []
    U = []
    for i in range(M):
        Z.append(Ls[i].dot(X))
        U.append(np.zeros_like(Z[i]))
    all_errors = []
    history = []

    for it in range(max_iter):
        # Optionally store the current state
        if traceback:
            history.append(X)

        # Update the variables
        X, Z_, U, LX = utils.update_variables(X, Z, U, prox_f, step_f, proxs_g, steps_g, Ls)
        # ADMM Convergence Criteria, adapted from Boyd 2011, Sec 3.3.1
        convergence, errors = utils.check_constraint_convergence(step_f, steps_g, X, LX, Z_, Z, U, Ls, e_rel)
        Z = Z_

        if traceback:
            all_errors.append(errors)

        if convergence:
            break

    # undo matrix adaptor
    for i in range(M):
        Ls[i] = Ls[i].L

    if it+1 == max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))

    if not traceback:
        return X
    else:
        tr = utils.Traceback(it=it, Z=Z, U=U, errors=all_errors, history=history)
        return X, tr


def update_steps(it, allXk, constraints, step_beta, wmax=1):
    """Calculate the Lipschitz constants to calculate the steps for each variable
    """
    lipschitz = [utils.lipschitz_const(Xk) for Xk in allXk]
    steps = [step_beta**it/np.prod(lipschitz[:n]+lipschitz[n+1:])/wmax for n in range(len(allXk))]
    return steps

def als(allX, all_prox_f, all_prox_g, all_constraints, max_iter=500,
        e_rel=1e-3, step_beta=1., weights=1, all_step_g=None, all_constraint_norms=None,
        traceback=False, convergence_func=None, als_max_iter=50, algorithms=None, min_iter=10,
        dot_components=np.dot, **kwargs):
    """Use alternating least squares to minimize a function with multiple variables
    """
    # Initialize the parameters
    nbr_variables = len(allX)
    if np.isscalar(weights):
        wmax = weights
    else:
        wmax = weights.max()
    if np.isscalar(e_rel):
        e_rel = [e_rel]*len(allX)
    # If the user didn't specify a function to check for convergence use the default
    if convergence_func is None:
        check_convergence = [utils.check_convergence]*len(allX)
    # If there is only a single convergence function, use it for all of the variables
    elif not hasattr(convergence_func, '__len__'):
        check_convergence = [convergence_func]*len(allX)
    else:
        check_convergence = convergence_func

    # Initialize the variables
    allXk = [X.copy() for X in allX]

    # If no algorithms are specified, automatically detect the best to use
    # (may differ for each variable)
    if algorithms is None:
        algorithms = [None]*len(allX)
    logger.debug("all_constraints: {0}".format(all_constraints))
    for n, constraints in enumerate(all_constraints):
        if algorithms[n] is None:
            if constraints is None or len(constraints)==0:
                # TODO: Implement fix to not use APGM
                #if all_prox_g[n] is not None:
                    algorithms[n] = "APGM"
                # else: keep algorithms[n]=None, to just use prox_f to update the variable
            elif len(constraints)==1:
                algorithms[n] = "ADMM"
            else:
                algorithms[n] = "SDMM"

    # Optionally keep track of the variable history
    history = []
    # Main loop
    all_errors = []
    all_norms = []
    for it in range(als_max_iter):
        f_steps = update_steps(it, allXk, constraints, step_beta, wmax)
        iterations = np.zeros(nbr_variables)
        _allXk = [Xk.copy() for Xk in allXk]
        _allZk = []
        _allUk = []
        if all_step_g is None:
            g_steps = [f_steps[n]*all_constraint_norms[n] for n in range(len(f_steps))]
        else:
            g_steps = all_step_g
        for n,algorithm in enumerate(algorithms):
            if algorithm is None:
                raise Exception("Not yet implemented")
            else:
                # Include all of the variables and the index of the current variable, as well as
                # any other keyword arguments the user might need to calculate prox_f and prox_g
                prox_f = partial(all_prox_f[n], allX=_allXk, **kwargs)
                # TODO: This is a temporary fix that allows the code to run with no prox_g
                # Remove and fix later
                if all_constraints[n] is None:
                    from . import proximal
                    prox_g = proximal.prox_id
                else:
                    prox_g = [partial(prox, allX=_allXk, **kwargs) for prox in all_prox_g[n]]
                # It is possible to use a different product for each operator,
                # but if a single component is specified, use it for all of the variables
                if hasattr(dot_components, '__len__'):
                    dci = dot_components[n]
                else:
                    dci = dot_components
                # Setup the variables for the different algorithms
                if algorithm == "APGM":
                    al = apgm
                    constraints = None
                if algorithm == "ADMM":
                    al = admm
                    constraints = all_constraints[n][0]
                    prox_g = prox_g[0]
                    if hasattr(dci, '__len__'):
                        dci = dci[0]
                if algorithm == "SDMM":
                    al = sdmm
                    constraints = all_constraints[n]
                    if not hasattr(dci, "__len__"):
                        dci = [dci]*len(constraints)
                # Calculate Xk, Zk, Uk for the current step
                result = al(X0=allXk[n], prox_f=prox_f, step_f=f_steps[n],
                            prox_g=prox_g, step_g=g_steps[n],
                            constraints=constraints, max_iter=max_iter, e_rel=e_rel[n],
                            dot_components=dci)
                iterations[n], _allXk[n], _Zk, _Uk, errors = result
                _allZk.append(_Zk)
                _allUk.append(_Uk)
        # If none of the variables required any iterations
        if np.all([n==0 for n in iterations]):
            logger.info("{0}: convergence: {1}, iterations: {2}".format(it, all_convergence, iterations))
            break
        # Optionally store the current state
        if traceback:
            history.append([_allXk, _allZk, _allUk])
        ## Convergence crit from Langville 2014, section 5 ?
        iter_norms = []
        all_convergence = []
        for n,_Xk in enumerate(_allXk):
            convergence, norms = check_convergence[n](it, _Xk, allXk[n], e_rel[n], min_iter)
            iter_norms.append(norms)
            all_convergence.append(convergence)
        logger.info("{0}: convergence: {1}, iterations: {2}".format(it, all_convergence, iterations))
        # Exit the loop if the convergence criteria has been meet
        if np.all(all_convergence):
            break

        all_errors += errors
        all_norms.append(iter_norms)
        allXk = [X.copy() for X in _allXk]
    if it+1==als_max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))
    return allXk, [all_norms, all_errors], history

def glmm(allX, all_prox_f, all_prox_g, all_constraints, max_iter=500,
        e_rel=1e-3, step_beta=1., weights=1, all_step_g=None, all_constraint_norms=None,
        traceback=False, convergence_func=None, min_iter=10, dot_components=np.dot, **kwargs):
    """Use the Generalized Linearization Method of Multipliers
    """
    # Initialize the parameters
    nbr_variables = len(allX)
    if np.isscalar(weights):
        wmax = weights
    else:
        wmax = weights.max()
    if np.isscalar(e_rel):
        e_rel = [e_rel]*len(allX)
    # It is possible to use a different product for each operator,
    # but if a single component is specified, use it for all of the variables
    if hasattr(dot_components, '__len__'):
        all_dot_components = dot_components
    else:
        all_dot_components = [None if constraints is None else [dot_components]*len(constraints)
                                    for constraints in all_constraints]

    # Initialize the variables
    allXk = [X.copy() for X in allX]
    # Initialize the primal and dual variables
    allZk = []
    allUk = []
    for n, X in enumerate(allXk):
        constraints = all_constraints[n]
        if constraints is None or len(constraints)==0:
            allZk.append(X.copy())
            allUk.append(np.zeros_like(X))
        else:
            shape = [len(constraints)]+list(X.shape)
            allZk.append(np.zeros(shape))
            allUk.append(np.zeros_like(allZk[-1]))

    # Optionally keep track of the variable history
    history = []
    # Main loop
    all_errors = []
    all_norms = []
    for it in range(max_iter):
        # Set the steps for the f and g proximal operators
        f_steps = update_steps(it, allXk, constraints, step_beta, wmax)
        if all_step_g is None:
            g_steps = [f_steps[n]*all_constraint_norms[n] for n in range(len(f_steps))]
        else:
            g_steps = all_step_g
        # Initialize the variables for the k+1 iteration
        iterations = np.zeros(nbr_variables)
        _allXk = [X.copy() for X in allXk]
        _allZk = [None if Z is None else Z.copy() for Z in allZk]
        allCX = []
        # Calculate _X{k+1} for all of the variables
        for n in range(nbr_variables):
            #logger.debug("var {0} prox_g: {1}".format(n, all_prox_g[n]))
            _prox_f = partial(all_prox_f[n], allX=_allXk, **kwargs)
            if all_constraints[n] is not None:
                # Get the proximal operators for each constraint
                _prox_g = [partial(prox, allX=_allXk, **kwargs) for prox in all_prox_g[n]]
                result = utils.update_variables(allXk[n], allZk[n], allUk[n], _prox_f, f_steps[n],
                                                _prox_g, g_steps[n], all_constraints[n],
                                                all_dot_components[n])
                _allXk[n], _allZk[n], allUk[n], CX = result
                allCX.append(CX)
            else:
                # Use the simplified algorithm without a linear constraint
                _allXk[n] = _prox_f(_allXk[n], f_steps[n])
                _allZk[n] = None
                allUk[n] = None
                allCX.append(None)
                #_allXk[n] = _prox_f(_allZk[n]-allUk[n], f_steps[n])
                #_allZk[n] = _prox_g(_allXk[n]+allUk[n], f_steps[n])
                #allUk[n] = allUk[n] + _allXk[n] - _allZk[n]
        # Optionally store the current state
        if traceback:
            history.append([_allXk, _allZk, allUk])
        # Convergence crit from Langville 2014, section 5 ?
        iter_norms = []
        likelihood_convergence = []
        for n,Xk_ in enumerate(_allXk):
            convergence, norms = utils.check_convergence(it, Xk_, allXk[n], e_rel[n], min_iter)
            iter_norms.append(norms)
            likelihood_convergence.append(convergence)
        # ADMM Convergence Criteria, adapted from Boyd 2011, Sec 3.3.1
        admm_convergence = [True]*len(all_constraints)
        iter_errors = []
        for n, Xk_ in enumerate(_allXk):
            if all_constraints[n] is not None:
                result = utils.check_constraint_convergence(f_steps[n], g_steps[n], Xk_, allCX[n], _allZk[n],
                                                            allZk[n],allUk[n], all_constraints[n], e_rel[n],
                                                            all_dot_components[n])
                admm_convergence[n], errors = result
                iter_errors.append(errors)

        # Store the errors
        all_errors.append(iter_errors)
        all_norms.append(iter_norms)

        # Update all of the variables
        allXk = [X.copy() for X in _allXk]
        allZk = [None if Z is None else Z.copy() for Z in _allZk]

        # If the likelhoods and the dual and primal variables have converged, exit the loop
        if np.all(likelihood_convergence) and np.all(admm_convergence) and it>min_iter:
            break
    if it+1==max_iter:
        logger.warning("Solution did not converge")
    logger.info("Completed {0} iterations".format(it+1))
    return allXk, [all_norms, all_errors], history
