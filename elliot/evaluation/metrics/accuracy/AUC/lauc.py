"""
This is the implementation of the Limited AUC metric.
It proceeds from a user-wise computation, and average the values over the users.
"""

__version__ = '0.1'
__author__ = 'Vito Walter Anelli, Claudio Pomo'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it'

import numpy as np
from evaluation.metrics.base_metric import BaseMetric


class LAUC(BaseMetric):
    """
    This class represents the implementation of the Limited AUC recommendation metric.
    Passing 'LAUC' to the metrics list will enable the computation of the metric.
    """

    def __init__(self, recommendations, config, params, eval_objects):
        """
        Constructor
        :param recommendations: list of recommendations in the form {user: [(item1,value1),...]}
        :param config: SimpleNameSpace that represents the configuration of the experiment
        :param params: Parameters of the model
        :param eval_objects: list of objects that may be useful for the computation of the different metrics
        """
        super().__init__(recommendations, config, params, eval_objects)
        self._cutoff = self._evaluation_objects.cutoff
        self._relevant_items = self._evaluation_objects.relevance.get_binary_relevance()
        self._num_items = self._evaluation_objects.num_items

    @staticmethod
    def name():
        """
        Metric Name Getter
        :return: returns the public name of the metric
        """
        return "LAUC"

    @staticmethod
    def __user_auc_at_k(user_recommendations, cutoff, user_relevant_items, num_items, train_size):
        """
        Per User Limited AUC
        :param user_recommendations: list of user recommendation in the form [(item1,value1),...]
        :param cutoff: numerical threshold to limit the recommendation list
        :param user_relevant_items: list of user relevant items in the form [item1,...]
        :return: the value of the Precision metric for the specific user
        """
        neg_num = num_items - train_size - len(user_relevant_items) + 1
        pos_ranks = [r for r, (i, _) in enumerate(user_recommendations[:cutoff]) if i in user_relevant_items]
        return sum([(neg_num - r_r + p_r)/(neg_num) for p_r, r_r in enumerate(pos_ranks)])/min(cutoff, len(user_relevant_items))

    def eval(self):
        """
        Evaluation function
        :return: the overall averaged value of LAUC
        """

        return np.average(
            [LAUC.__user_auc_at_k(u_r, self._cutoff, self._relevant_items[u], self._num_items, len(self._evaluation_objects.data.train_dict[u]))
             for u, u_r in self._recommendations.items()]
        )

    def eval_user_metric(self):
        """
        Evaluation function
        :return: the overall averaged value of LAUC per user
        """
        return {u: LAUC.__user_auc_at_k(u_r, self._cutoff, self._relevant_items[u], self._num_items, len(self._evaluation_objects.data.train_dict[u]))
             for u, u_r in self._recommendations.items()}

