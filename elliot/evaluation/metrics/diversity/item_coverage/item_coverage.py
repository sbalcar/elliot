"""
This is the implementation of the Item Coverage metric.
It directly proceeds from a system-wise computation, and it considers all the users at the same time.
"""

__version__ = '0.1'
__author__ = 'Vito Walter Anelli, Claudio Pomo'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it'

from evaluation.metrics.base_metric import BaseMetric


class ItemCoverage(BaseMetric):
    """
    This class represents the implementation of the Item Coverage recommendation metric.
    Passing 'ItemCoverage' to the metrics list will enable the computation of the metric.
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

    @staticmethod
    def name():
        """
        Metric Name Getter
        :return: returns the public name of the metric
        """
        return "ItemCoverage"

    def eval(self):
        """
        Evaluation function
        :return: the overall averaged value of Item Coverage
        """
        return len({i[0] for u_r in self._recommendations.values() for i in u_r[:self._cutoff]})
