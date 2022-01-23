"""
Module description:

"""

__version__ = '0.3.0'
__author__ = 'Vito Walter Anelli, Claudio Pomo, Daniele Malitesta, Felice Antonio Merra'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it, daniele.malitesta@poliba.it, felice.merra@poliba.it'

from abc import ABC

from .FeatureProjection import FeatureProjection
from .DisenGCNLayer import DisenGCNLayer
from collections import OrderedDict

import torch
import torch_geometric
import numpy as np


class DisenGCNModel(torch.nn.Module, ABC):
    def __init__(self,
                 num_users,
                 num_items,
                 learning_rate,
                 embed_k,
                 l_w,
                 weight_size,
                 n_layers,
                 disen_k,
                 temperature,
                 routing_iterations,
                 message_dropout,
                 edge_index,
                 random_seed,
                 name="DisenGCN",
                 **kwargs
                 ):
        super().__init__()
        torch.manual_seed(random_seed)

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.num_users = num_users
        self.num_items = num_items
        self.embed_k = embed_k
        self.learning_rate = learning_rate
        self.l_w = l_w
        self.weight_size = weight_size
        self.n_layers = n_layers
        self.disen_k = disen_k
        self.temperature = temperature
        self.routing_iterations = routing_iterations
        self.message_dropout = message_dropout if message_dropout else [0.0] * self.n_layers
        self.weight_size_list = [self.embed_k] + self.weight_size
        self.edge_index = torch.tensor(edge_index, dtype=torch.int64)

        self.Gu = torch.nn.Parameter(
            torch.nn.init.zeros_(torch.empty((self.num_users, self.embed_k))))
        self.Gu.to(self.device)
        self.Gi = torch.nn.Parameter(
            torch.nn.init.zeros_(torch.empty((self.num_items, self.embed_k))))
        self.Gi.to(self.device)

        disengcn_network_list = []
        for layer in range(self.n_layers):
            projection_layer = torch.nn.Sequential(OrderedDict([('feat_proj_' + str(layer), (FeatureProjection(
                self.weight_size_list[layer],
                self.weight_size_list[layer + 1],
                self.disen_k[layer])))]))
            disentangle_layer = torch_geometric.nn.Sequential('x, edge_index', [
                (DisenGCNLayer(self.temperature), 'x, edge_index -> x')])
            disengcn_network_list.append(('disen_gcn_' + str(layer), torch.nn.Sequential(projection_layer,
                                                                                         disentangle_layer)))
            disengcn_network_list.append(('dropout_' + str(layer), torch.nn.Dropout(self.message_dropout[layer])))

        self.disengcn_network = torch.nn.Sequential(OrderedDict(disengcn_network_list))
        self.disengcn_network.to(self.device)
        self.softplus = torch.nn.Softplus()

        self.optimizer = torch.optim.Adam(self.parameters(), lr=self.learning_rate)

    def propagate_embeddings(self, evaluate=False):
        current_embeddings = torch.cat((self.Gu.to(self.device), self.Gi.to(self.device)), 0)
        for layer in range(0, self.n_layers * 2, 2):
            if not evaluate:
                current_embeddings = list(self.disengcn_network.children())[layer][0](current_embeddings.to(self.device))
                for _ in range(self.routing_iterations):
                    current_embeddings = list(self.disengcn_network.children())[layer][1](current_embeddings.to(self.device),
                                                                                          self.edge_index.to(self.device))
                current_embeddings = torch.reshape(current_embeddings, [current_embeddings.shape[0], 
                                                                        current_embeddings.shape[1] * current_embeddings.shape[2]])
                current_embeddings = list(self.disengcn_network.children())[layer + 1](current_embeddings.to(self.device))
            else:
                self.disengcn_network.eval()
                with torch.no_grad():
                    current_embeddings = list(self.disengcn_network.children())[layer][0](current_embeddings.to(self.device))
                    for _ in range(self.routing_iterations):
                        current_embeddings = list(self.disengcn_network.children())[layer][1](current_embeddings.to(self.device),
                                                                                            self.edge_index.to(self.device))
                    current_embeddings = torch.reshape(current_embeddings, [current_embeddings.shape[0], 
                                                                            current_embeddings.shape[1] * current_embeddings.shape[2]])
                    current_embeddings = list(self.disengcn_network.children())[layer + 1](current_embeddings.to(self.device))

        if evaluate:
            self.disengcn_network.train()

        gu, gi = torch.split(current_embeddings, [self.num_users, self.num_items], 0)
        return gu, gi


    def forward(self, inputs, **kwargs):
        gu, gi = inputs
        gamma_u = torch.squeeze(gu).to(self.device)
        gamma_i = torch.squeeze(gi).to(self.device)

        xui = torch.sum(gamma_u * gamma_i, 1)

        return xui

    def predict(self, gu, gi, **kwargs):
        return torch.matmul(gu.to(self.device), torch.transpose(gi.to(self.device), 0, 1))

    def train_step(self, batch):
        gu, gi = self.propagate_embeddings()
        user, pos, neg = batch
        xu_pos = self.forward(inputs=(gu[user], gi[pos]))
        xu_neg = self.forward(inputs=(gu[user], gi[neg]))

        difference = torch.clamp(xu_pos - xu_neg, -80.0, 1e8)
        loss = torch.sum(self.softplus(-difference))
        reg_loss = self.l_w * (torch.norm(self.Gu, 2) +
                               torch.norm(self.Gi, 2) +
                               torch.stack([torch.norm(value, 2) for value in self.disengcn_network.parameters()],
                                           dim=0).sum(dim=0)) * 2
        loss += reg_loss

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.detach().cpu().numpy()

    def get_top_k(self, preds, train_mask, k=100):
        return torch.topk(torch.where(torch.tensor(train_mask).to(self.device), preds.to(self.device),
                                      torch.tensor(-np.inf).to(self.device)), k=k, sorted=True)
