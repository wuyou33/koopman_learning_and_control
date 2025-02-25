import numpy as np
from numba import jit
from koopman_core.controllers import NonlinearMPCControllerNb

@jit(nopython=True)
def _update_linearization(A_flat, B_flat, B_arr, z_init, u_init, nx, N):
    A_lst = np.dot(u_init, B_flat) + A_flat
    A_lst_flat = A_lst.flatten()
    B_lst_flat = (np.dot(z_init[:-1, :], B_arr)).flatten()

    A_reshaped = A_lst.reshape(nx * N, nx)
    r_vec = np.empty((N, nx))
    for i in range(N):
        r_vec[i, :] = np.dot(z_init[i, :], A_reshaped[i*nx:(i+1)*nx, :])
    r_vec = (r_vec - z_init[1:, :]).flatten()

    return A_lst_flat, B_lst_flat, r_vec

class BilinearMPCControllerNb(NonlinearMPCControllerNb):
    """
    Class for bilinear MPC.
    Quadratic programs are solved using OSQP.
    """

    def __init__(self, dynamics, N, dt, umin, umax, xmin, xmax, Q, R, QN, xr, solver_settings, const_offset=None,
                 terminal_constraint=False, add_slack=False, q_slack=1e3):

        super(BilinearMPCControllerNb, self).__init__(dynamics, N, dt, umin, umax, xmin, xmax, Q, R, QN, xr, solver_settings,
                                        const_offset=const_offset,
                                        terminal_constraint=terminal_constraint,
                                        add_slack=add_slack,
                                        q_slack=q_slack)

        self.embed_pkg_str = 'knmpc_' + str(self.nx) + '_' + str(self.nu) + '_' + str(self.N)
        self.A_flat = self.dynamics_object.A.flatten(order='F')
        self.B_flat = np.array([b.flatten(order='F') for b in self.dynamics_object.B])
        self.B_arr = np.vstack(self.dynamics_object.B).T

    def update_constraint_matrix_data_(self, A_lst, B_lst):
        self._osqp_A_data[self._osqp_A_data_A_inds] = A_lst
        self._osqp_A_data[self._osqp_A_data_B_inds] = B_lst

    def update_linearization_(self):
        A_lst_flat, B_lst_flat, self.r_vec[:] = _update_linearization(self.A_flat, self.B_flat, self.B_arr,
                                                                   self.z_init, self.u_init, self.nx, self.N)

        return A_lst_flat, B_lst_flat

    def get_state_prediction(self):
        """
        Get the state prediction from the MPC problem
        :return: Z (np.array) current state prediction
        """
        if self.dynamics_object.standardizer_x is None:
            return (self.dynamics_object.C@self.cur_z.T).T
        else:
            return self.dynamics_object.standardizer_x.inverse_transform((self.dynamics_object.C@self.cur_z.T).T)

    def get_control_prediction(self):
        if self.dynamics_object.standardizer_u is None:
            return self.cur_u
        else:
            return self.dynamics_object.standardizer_u.inverse_transform(self.cur_u)