#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 18 14:58:06 2019

@author: Filip Maciejewski
email: filip.b.maciejewski@gmail.com

#TODO FBM: Some functions used here come from other packages - we probably need to identify them and copy to some
    "helper_functions_QDT" repository
"""

import povmtools
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
import itertools


def get_list_of_lists_indices_qdt(qubits_indices, unitaries_amount):
    """
    Description:
    From list of qubit indices and number of unitaries, prepare set of names for circuits for tomography of
    detectors.

    # TODO FBM: Maybe GeneralTensor could be used for it?
    # TR: It now is -- check it out ;)

    :param qubits_indices: (list of ints) labels of qubits for QDT
    :param unitaries_amount: (int) number of unitaries you want to implement.

    :return: (list of lists of pairs of number [qubit_label, unitary_label]) of length
    unitaries_amount**len(qubits_indices)

    For example, let's assume we have three qubits [0,2,4] and we have 4 unitaries. For concreteness, if those unitaries
    are [id, X, H, SH] for creation of [|0>, |1>, |+x>, |+y>] states, the circuits will be:

    id x id x id,
    -------------
    id x id x X,
    -------------
    id x id x H,
    -------------
    id x id x SH,
    -------------

    id x X x id
    -------------
    id x X x X
    -------------
    id x X x H
    -------------
    id x X x SH
    -------------

    etc....

    SH x SH x id
    -------------
    SH x SH x X
    -------------
    SH x SH x H
    -------------
    SH x SH x SH

    If unitaries are ordered as [id, X, H, SH], the code will identify id: 0, X: 1, H: 2, SH:3, and it will return a
    list of lists. Each list correspond to single line in the above exemplary description of tensor product, e.g.,
    second list corresponds to line id x id x X. Each of such lists consists of len(qubits_indices) pairs, saying which
    gate shall be applied to which qubit. In this example, first list will have following elements:
    (0, 0), (2, 0), (4, 1), i.e., apply unitary number 0 to qubits 0,2 and apply unitary number 1 to qubit 4.
    """

    qubits_number = len(qubits_indices)

    # number unitaries from 0 to unitaries_amount-1
    unitaries_indices = range(unitaries_amount)

    # create Cartesian product of labels for qubits and unitaries
    qubits_and_unitaries = list(itertools.product(qubits_indices, unitaries_indices))

    # take lists corresponding to particular qubits
    single_qubit_unitaries = [qubits_and_unitaries[i * unitaries_amount:(i + 1) * unitaries_amount] for i in
                              range(qubits_number)]

    # get all possible combinations of qubit+gate pairs
    list_of_gates = single_qubit_unitaries[0]
    for i in np.arange(1, qubits_number):
        list_of_gates = list(itertools.product(list_of_gates, single_qubit_unitaries[i]))

    # TODO FBM: this code could end here if I knew how to flatten list of itertools.product() s in a simple manner.
    #  Without next steps the list is a very nested tuple of tuples

    def flatten(container):
        # lame flattener
        for i in container:
            if isinstance(i, list) or isinstance(i, tuple):
                for j in flatten(i):
                    yield j
            else:
                yield i

    # flatten everything
    list_of_gates = list(flatten(list(list_of_gates)))

    # now put it back together in two steps
    single_circuit_description_length = qubits_number * 2

    # take sublists of length 2*qubits_number (one index for qubit and one index for unitary)
    almost_final_list = [
        list_of_gates[i * single_circuit_description_length:(i + 1) * single_circuit_description_length] for i in
        range(int(len(list_of_gates) / single_circuit_description_length))]

    final_list = []
    # create final list of lists for which entries are pairs (qubit_index, unitary_index)
    for l in almost_final_list:
        final_list.append([l[i * 2:(i + 1) * 2] for i in range(int(len(l) / 2))])

    return final_list


def detector_tomography_circuits(qubit_indices,
                                 probe_kets,
                                 number_of_repetitions=1):
    """From list of probe kets and qubit data return quantum circuits which will be implemented to perform
    Quantum Detector Tomography (QDT).

    :param probe_kets: (list of numpy arrays) the list of ket representations of qubit pure quantum states which are to
    be used in QDT. For multi-qubit QDT, the combinations of tensor products of name_appendix will be taken.
    :param qubit_indices: (list of ints) labels of qubits for QDT
    :param number_of_repetitions: (int) parameter specifying how many copies of whole QDT experiment should be created
    (for larger statistics collection or comparision of results)

    :return: (list of QuantumCircuit objects) of length len(probe_states)**(number_of_qubits)
    """

    qubit_indices = sorted(qubit_indices)  # Sort to ensure, that results can easily be interpreted.
    tomography_circuits = []
    unitaries = [povmtools.get_unitary_change_ket_qubit(ket) for ket in probe_kets]

    # create nice list with proper ordering of circuits. In first step, last qubit in list qubit_indices is iterated
    # while all the other are fixed. See function description for details.
    indices_for_circuits = get_list_of_lists_indices_qdt(qubit_indices, len(unitaries))

    qrs = max(qubit_indices) + 1

    # outer loop is for copies of QDT experiment
    for number in range(number_of_repetitions):

        # inner loop goes through all circuits in QDT experiments and prepares them
        for index_for_set in range(len(indices_for_circuits)):

            # index of set of qubits+unitaries for current step
            current_set = indices_for_circuits[index_for_set]

            # create quantum register
            qreg = QuantumRegister(qrs)
            creg = ClassicalRegister(len(qubit_indices))

            # create quantum circuit
            circuit = QuantumCircuit(qreg, creg)

            # get barrier to prevent compiler from making changes
            circuit.barrier()

            for qubit_unitary_pair_index in range(len(current_set)):

                # take qubit+unitary pair
                pair_now = current_set[qubit_unitary_pair_index]

                # take index of qubit and index of unitary
                q_now_index, u_now_index = pair_now[0], pair_now[1]

                # make sure that chosen quantum state is not one of the states in computational basis
                # TODO: this might not be necessary anymore, it's an old code, I had some problems long time ago with
                #  those guys because qiskit compiler went crazy if I defined identity or x gate using u3 unitary.
                if povmtools.check_if_projector_is_in_computational_basis(povmtools.get_density_matrix(probe_kets[u_now_index])):
                    if povmtools.get_density_matrix(probe_kets[u_now_index])[0][0] == 1:
                        circuit.iden(qreg[q_now_index])
                    elif povmtools.get_density_matrix(probe_kets[u_now_index])[1][1] == 1:
                        circuit.x(qreg[q_now_index])
                    else:
                        raise ValueError('error')
                else:
                    # get angles for single-qubit state change unitary
                    current_angles = povmtools.get_su2_parametrizing_angles(unitaries[u_now_index])

                    # implement unitary
                    circuit.u3(current_angles[0],
                               current_angles[1],
                               current_angles[2], qreg[q_now_index])

            # Add measurements
            for i in range(len(qubit_indices)):
        
                
                circuit.measure(qreg[qubit_indices[i]], creg[i])

            tomography_circuits.append(circuit)
    return tomography_circuits


from PyMaLi import GeneralTensorCalculator


def gtc_tensor_calculating_function(arguments: list):
    result = []

    for a in arguments:
        result.append(a)

    return result


def detector_tomography_circuits_pymali(qubit_indices, probe_kets):
    """
    Analogical version of the circuits preparing method utilizing pymali general tensor calculator.
    """

    qubit_indices = sorted(qubit_indices)  # Sort to ensure, that results can easily be interpreted.
    tomography_circuits = []
    unitaries = [povmtools.get_unitary_change_ket_qubit(ket) for ket in probe_kets]

    # create nice list with proper ordering of circuits. In first step, last qubit in list qubit_indices is iterated
    # while all the other are fixed. See function description for details.
    gtc = GeneralTensorCalculator.GeneralTensorCalculator(gtc_tensor_calculating_function)
    unitaries_lists_for_tensor_calculator = [unitaries.copy() for i in range(len(qubit_indices))]
    list_of_unitaries_sets = gtc.calculate_tensor_to_increasing_list(unitaries_lists_for_tensor_calculator)
    qrs = max(qubit_indices) + 1

    # inner loop goes through all circuits in QDT experiments and prepares them
    for unitaries_set in list_of_unitaries_sets:

        qreg = QuantumRegister(qrs)
        creg = ClassicalRegister(len(qubit_indices))

        circuit = QuantumCircuit(qreg, creg)
        circuit.barrier()  # To prevent compiler from making changes.

        for j in range(len(unitaries_set)):

            current_angles = povmtools.get_su2_parametrizing_angles(unitaries_set[j])

            # TODO TR: I believe there may be more "special" cases. If so, then this should be placed in other method
            #  or in get_su2_ ... method.
            if current_angles[0] == 'id':
                circuit.iden(qreg[qubit_indices[j]])
                continue
            if current_angles[0] == 'x':
                circuit.x(qreg[qubit_indices[j]])
                continue

            # implement unitary
            circuit.u3(current_angles[0],
                       current_angles[1],
                       current_angles[2], qreg[qubit_indices[j]])

        # Add measurements
        for i in range(len(qubit_indices)):
            circuit.measure(qreg[qubit_indices[i]], creg[i])

        tomography_circuits.append(circuit)
    return tomography_circuits
