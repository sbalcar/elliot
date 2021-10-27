"""
Module description:

"""

__version__ = '0.3.0'
__author__ = 'Vito Walter Anelli, Claudio Pomo, Daniele Malitesta, Felice Antonio Merra'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it, daniele.malitesta@poliba.it, felice.merra@poliba.it'

from ast import literal_eval as make_tuple

from tqdm import tqdm
import numpy as np

from elliot.dataset.samplers import custom_sampler as cs
from elliot.recommender import BaseRecommenderModel
from elliot.recommender.base_recommender_model import init_charger
from elliot.recommender.recommender_utils_mixin import RecMixin
from .MMGCNModel import MMGCNModel


class MMGCN(RecMixin, BaseRecommenderModel):
    r"""
    MMGCN: Multi-modal Graph Convolution Network for Personalized Recommendation of Micro-video

    For further details, please refer to the `paper <https://dl.acm.org/doi/10.1145/3343031.3351034>`_

    Args:
        lr: Learning rate
        epochs: Number of epochs
        factors: Number of latent factors
        factors_multimod: Tuple with number of units for each modality
        batch_size: Batch size
        l_w: Regularization coefficient
        weight_size: Tuple with number of units for each embedding propagation layer
        modalities: Tuple of modalities
        aggregation: Type of aggregation
        combination: Type of combination

    To include the recommendation model, add it to the config file adopting the following pattern:

    .. code:: yaml

      models:
        MMGCN:
          meta:
            save_recs: True
          lr: 0.0005
          epochs: 50
          factors: 64
          factors_multimod: (64,64)
          batch_size: 256
          l_w: 0.1
          weight_size: (64,)
          modalities: (visual,textual)
          aggregation: mean
          combination: co
    """

    @init_charger
    def __init__(self, data, config, params, *args, **kwargs):

        self._sampler = cs.Sampler(self._data.i_train_dict)
        if self._batch_size < 1:
            self._batch_size = self._num_users

        ######################################

        self._params_list = [
            ("_learning_rate", "lr", "lr", 0.0005, float, None),
            ("_factors", "factors", "factors", 64, int, None),
            ("_l_w", "l_w", "l_w", 0.01, float, None),
            ("_weight_size", "weight_size", "weight_size", "(64,)", lambda x: list(make_tuple(x)),
             lambda x: self._batch_remove(str(x), " []").replace(",", "-")),
            ("_factors_multimod", "factors_multimod", "factors_multimod", "(64,64)", lambda x: list(make_tuple(x)),
             lambda x: self._batch_remove(str(x), " []").replace(",", "-")),
            ("_modalities", "modalities", "modalites", "('visual','textual')", lambda x: list(make_tuple(x)),
             lambda x: self._batch_remove(str(x), " []").replace(",", "-")),
            ("_aggregation", "aggregation", "aggregation", 'mean', str, None),
            ("_combination", "combination", "combination", 'co', str, None),
            ("_loaders", "loaders", "loads", "('VisualAttributes','TextualAttributes')", lambda x: list(make_tuple(x)),
             lambda x: self._batch_remove(str(x), " []").replace(",", "-"))
        ]
        self.autoset_params()

        self._n_layers = len(self._weight_size)

        for m_id, m in enumerate(self._modalities):
            self.__setattr__(f'''_side_{m}''',
                             self._data.side_information.__getattribute__(f'''{self._loaders[m_id]}'''))

        row, col = data.sp_i_train.nonzero()
        col = [c + self._num_users for c in col]
        self.edge_index = np.array([row, col])

        self._model = MMGCNModel(
            num_users=self._num_users,
            num_items=self._num_items,
            learning_rate=self._learning_rate,
            embed_k=self._factors,
            embed_k_multimod=self._factors_multimod,
            l_w=self._l_w,
            weight_size=self._weight_size,
            modalities=self._modalities,
            aggregation=self._aggregation,
            combination=self._combination,
            multimodal_features=[self.__getattribute__(f'''_side_{m}''').object.get_all_features() for m in
                                 self._modalities],
            n_layers=self._n_layers,
            edge_index=self.edge_index,
            random_seed=self._seed
        )

    @property
    def name(self):
        return "MMGCN" \
               + f"_{self.get_base_params_shortcut()}" \
               + f"_{self.get_params_shortcut()}"

    def train(self):
        if self._restore:
            return self.restore_weights()

        for it in self.iterate(self._epochs):
            loss = 0
            steps = 0
            with tqdm(total=int(self._data.transactions // self._batch_size), disable=not self._verbose) as t:
                for batch in self._sampler.step(self._data.transactions, self._batch_size):
                    steps += 1
                    loss += self._model.train_step(batch)
                    t.set_postfix({'loss': f'{loss / steps:.5f}'})
                    t.update()

            self.evaluate(it, loss / (it + 1))

    def get_recommendations(self, k: int = 100):
        predictions_top_k_test = {}
        predictions_top_k_val = {}
        gu, gi = self._model.propagate_embeddings(evaluate=True)
        for index, offset in enumerate(range(0, self._num_users, self._batch_size)):
            offset_stop = min(offset + self._batch_size, self._num_users)
            predictions = self._model.predict(gu[offset: offset_stop], gi)
            recs_val, recs_test = self.process_protocol(k, predictions, offset, offset_stop)
            predictions_top_k_val.update(recs_val)
            predictions_top_k_test.update(recs_test)
        return predictions_top_k_val, predictions_top_k_test

    def get_single_recommendation(self, mask, k, predictions, offset, offset_stop):
        v, i = self._model.get_top_k(predictions, mask[offset: offset_stop], k=k)
        items_ratings_pair = [list(zip(map(self._data.private_items.get, u_list[0]), u_list[1]))
                              for u_list in list(zip(i.detach().cpu().numpy(), v.detach().cpu().numpy()))]
        return dict(zip(map(self._data.private_users.get, range(offset, offset_stop)), items_ratings_pair))
