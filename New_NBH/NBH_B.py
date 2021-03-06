import copy
import random
import time
import math
import numpy as np
import argparse
import os
import datetime
import torch
import torch.nn as nn
import torch.nn.functional as func
import torch.optim as optim
import torch.cuda

# 変更用オプション
#################################################################################
# 　d_はデフォルトの略、コマンドからの時は変更できる
d_EPOCH = 2000
# 格子点数および粒子数
d_LATTICE = 11
d_PARTICLE = 9
# パラメータ
d_U = 2
d_J = 1
# output アウトプットするデータの名前
d_OUTPUT_FILE_NAME = "AAA"
# GPUを使う場合'cuda' cpu なら'cpu'
d_GPU = 'cuda'

################################################################################

# 学習率
LR = 0.001
LR_STEP = 1000
LR_GAMMA = 0.1
MOMENTUM = 0.95
# 定数
MEMO_NAME = "memo.txt"  # 条件記録用
SAMPLE_NUM = 1000
net_num = 20
OUTPUT_NAME = "RESULT"
KILL_DATA = 50


# ニューラルネットワーク本体を作成
class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        # 全結合ネットワーク
        self.l1 = nn.Linear(LATTICE, net_num)
        self.l2 = nn.Linear(net_num, 2)

    def forward(self, x):
        # reluを用いる。
        h1 = torch.tanh(self.l1(x))
        y = self.l2(h1)
        return y


class MyLoss(nn.Module):
    def __init__(self, sample_num):
        super().__init__()
        self.i_vector_array = [np.arange(LATTICE) for i in range(sample_num)]
        self.i_vector_array = np.array(self.i_vector_array)
        self.i_vector_array = torch.from_numpy(self.i_vector_array)
        self.i_vector_array = self.i_vector_array.to(DEVICE)

    def forward(self, n_vector_array, cn_array, cn_tensor_1, cn_tensor_2, sample_num):
        cn_tensor_1 = (torch.exp(cn_tensor_1[:, :, 0]) * torch.exp(cn_tensor_1[:, :, 1] * 1j)) / (
                torch.exp(cn_array[:, 0]) * torch.exp(cn_array[:, 1] * 1j))
        cn_tensor_2 = (torch.exp(cn_tensor_2[:, :, 0]) * torch.exp(cn_tensor_2[:, :, 1] * 1j)) / (
                torch.exp(cn_array[:, 0]) * torch.exp(cn_array[:, 1] * 1j))
        return (-J * torch.sum(torch.sqrt(n_vector_array[:, 0:LATTICE - 1] * (n_vector_array[:, 1:LATTICE] + 1)) *
                                torch.t(torch.conj(cn_tensor_1))
                                + torch.sqrt((n_vector_array[:, 0:LATTICE - 1] + 1) * n_vector_array[:, 1:LATTICE]) *
                                torch.t(torch.conj(cn_tensor_2)))
                + J * torch.sum(self.i_vector_array ** 2 * n_vector_array)
                - J * (LATTICE - 1) * torch.sum(self.i_vector_array * n_vector_array)
                + ((LATTICE - 1) ** 2 * J / 4 - U / 2) * torch.sum(n_vector_array)
                + U / 2 * torch.sum(n_vector_array ** 2)) / sample_num


def est_particle(n_vector_array, i, sample_num):
    return torch.sum(n_vector_array[:, i]) / sample_num


def metropolis(sample_num, my_net):
    # GPUを使う場合データを変換する。to(DEVICE)
    # 返すベクトル生成
    n_vector_array = np.zeros([sample_num, LATTICE])
    n_vector_array = torch.from_numpy(n_vector_array).float()
    n_vector_array = n_vector_array.to(DEVICE)
    # 操作用のベクトル
    temp_vector = np.zeros([LATTICE])
    temp_vector = torch.from_numpy(temp_vector).float()
    temp_vector = temp_vector.to(DEVICE)

    rand_idx = random.randrange(LATTICE)
    temp_vector[rand_idx] = PARTICLE
    for j in range(PARTICLE * 5):
        temp_vector = shuffle_vector(temp_vector)
    for i in range(sample_num + KILL_DATA):
        new_vector = shuffle_vector(temp_vector)
        a1 = torch.sum(temp_vector != 0)
        a2 = torch.sum(new_vector != 0)
        b1 = my_net(temp_vector)
        b1 = torch.exp(b1[0]) * torch.exp(b1[1] * 1j)
        b2 = my_net(new_vector)
        b2 = torch.exp(b2[0]) * torch.exp(b2[1] * 1j)
        alpha = (abs(b2) / abs(b1)) ** 2 * (a1 / a2)
        if alpha < random.random():
            new_vector = temp_vector
        if i >= KILL_DATA:
            n_vector_array[i - KILL_DATA] = new_vector
    return n_vector_array


def shuffle_vector(n_vector):
    result_n_vector = copy.deepcopy(n_vector)
    while True:
        down = random.randrange(LATTICE)
        if not result_n_vector[down] == 0:
            break
    while True:
        up = random.randrange(LATTICE)
        if not down == up:
            break
    result_n_vector[down] -= 1
    result_n_vector[up] += 1
    return result_n_vector


def make_sample(n_vector_array, sample_num):
    n_vector_tensor_1 = np.zeros([LATTICE - 1, sample_num, LATTICE])
    n_vector_tensor_1 = torch.from_numpy(n_vector_tensor_1).float()
    n_vector_tensor_1 = n_vector_tensor_1.to(DEVICE)
    n_vector_tensor_2 = np.zeros([LATTICE - 1, sample_num, LATTICE])
    n_vector_tensor_2 = torch.from_numpy(n_vector_tensor_2).float()
    n_vector_tensor_2 = n_vector_tensor_2.to(DEVICE)
    for i in range(LATTICE - 1):
        n_vector_tensor_1[i] = copy.deepcopy(n_vector_array)
        n_vector_tensor_1[i, :, i] -= 1
        n_vector_tensor_1[i, :, i + 1] += 1
        n_vector_tensor_2[i] = copy.deepcopy(n_vector_array)
        n_vector_tensor_2[i, :, i] += 1
        n_vector_tensor_2[i, :, i + 1] -= 1
    return n_vector_tensor_1, n_vector_tensor_2


def learning():
    # オプションを表示
    print('GPU: {}'.format(GPU))
    print('# epoch: {}'.format(EPOCH))
    print('# lattice_point_num: {}'.format(LATTICE))
    print('# particle_num: {}'.format(PARTICLE))
    print('# output_file: {}'.format(OUTPUT_FILE_NAME))
    print('')

    if not os.path.exists(OUTPUT_FILE_NAME):
        os.mkdir(OUTPUT_FILE_NAME)
    # 後からわかるようにメモを出力
    with open(OUTPUT_FILE_NAME + "/" + MEMO_NAME, mode='a') as f:
        now_time = datetime.datetime.now()
        f.write("\n" + __file__ + "が実行されました。 " + now_time.strftime('%Y/%m/%d %H:%M:%S') + "\n 使用されたデータ:")
        f.write("エポック数:" + str(EPOCH) + "\n ")
        f.write("GPU:" + str(GPU) + "\n ")
        f.write("lattice_point_num:" + str(LATTICE) + "\n ")
        f.write("particle_num:" + str(PARTICLE) + "\n ")
        f.write("Lr:" + str(LR) + "\n ")
        f.write("STEP:" + str(LR_STEP) + "\n ")
        f.write("Gamma:" + str(LR_GAMMA) + "\n ")
        f.write("Momentum:" + str(MOMENTUM) + "\n ")
    print("データロード開始")

    # ニューラルネットワークを実体化
    my_net: nn.Module = MyModel()
    my_net = my_net.to(DEVICE)
    # 最適化アルゴリズム
    optimizer = optim.SGD(params=my_net.parameters(), lr=LR, momentum=MOMENTUM)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=LR_STEP, gamma=LR_GAMMA)

    criterion = MyLoss(SAMPLE_NUM)

    # 学習結果の保存用
    history = {'train_loss': [], 'test_loss': [], 'now_time': [], }

    # 学習開始。エポック数だけ学習を繰り返す。
    for e in range(EPOCH):
        # 学習を行う。
        my_net.eval()
        with torch.no_grad():
            train_n_vector_array = metropolis(SAMPLE_NUM, my_net)
            train_n_vector_tensor_1, train_n_vector_tensor_2 = make_sample(train_n_vector_array, SAMPLE_NUM)
        my_net.train(True)
        optimizer.zero_grad()
        cn_array = my_net(train_n_vector_array)
        cn_tensor_1 = my_net(train_n_vector_tensor_1)
        cn_tensor_2 = my_net(train_n_vector_tensor_2)
        energy = criterion(train_n_vector_array, cn_array, cn_tensor_1, cn_tensor_2, SAMPLE_NUM)
        energy.backward()
        optimizer.step()
        train_loss = energy.item()
        scheduler.step()
        # テストを行う。
        if e % 10 == 0:
            history['train_loss'].append(train_loss)
            my_net.eval()
            with torch.no_grad():
                test_n_vector_array = metropolis(SAMPLE_NUM, my_net)
                test_n_vector_tensor_1, test_n_vector_tensor_2 = make_sample(test_n_vector_array, SAMPLE_NUM)
                cn_array = my_net(test_n_vector_array)
                cn_tensor_1 = my_net(test_n_vector_tensor_1)
                cn_tensor_2 = my_net(test_n_vector_tensor_2)
                energy = criterion(test_n_vector_array, cn_array, cn_tensor_1, cn_tensor_2, SAMPLE_NUM)
                test_loss = energy.item()
            history['test_loss'].append(test_loss)
            # 経過を記録して、表示。
            now_time = datetime.datetime.now()
            history['now_time'].append(now_time.strftime('%Y/%m/%d %H:%M:%S'))
            print('Train Epoch: {}/{} \t TrainLoss: {:.6f} \t TestLoss: {:.6f} \t time: {} \t lr:{}'
                  .format(e + 1, EPOCH, train_loss, test_loss, now_time.strftime('%Y/%m/%d %H:%M:%S'),
                          scheduler.get_last_lr()[0]))

    print("学習終了")
    # 予測を行う。
    my_net.eval()
    n_vector_result = np.zeros([LATTICE])
    with torch.no_grad():
        est_n_vector_array = metropolis(SAMPLE_NUM * 10, my_net)
        est_n_vector_tensor_1, est_n_vector_tensor_2 = make_sample(est_n_vector_array, SAMPLE_NUM * 10)
        cn_array = my_net(est_n_vector_array)
        cn_tensor_1 = my_net(est_n_vector_tensor_1)
        cn_tensor_2 = my_net(est_n_vector_tensor_2)
        energy = criterion(est_n_vector_array, cn_array, cn_tensor_1, cn_tensor_2, SAMPLE_NUM * 10)
        for i in range(LATTICE):
            n_vector_result[i] = est_particle(est_n_vector_array, i, SAMPLE_NUM * 10)
            est_loss = energy.item()

    # 結果をセーブする。
    if not os.path.exists(args.out + "/" + OUTPUT_NAME):
        os.mkdir(args.out + "/" + OUTPUT_NAME)
    torch.save(my_net.state_dict(), args.out + "/" + OUTPUT_NAME + "/" + 'model.pth')
    with open(args.out + "/" + OUTPUT_NAME + "/" + 'result.txt', mode='a') as f:
        f.write("\n \n " + str(est_loss))
        f.write("\n \n " + str(n_vector_result))
    with open(args.out + "/" + OUTPUT_NAME + "/" + 'history.txt', mode='a') as f:
        f.write("\n \n " + str(history))

    print("終了")
    # 終了時間メモ
    now_time = datetime.datetime.now()
    with open(args.out + "/" + MEMO_NAME, mode='a') as f:
        f.write("\n終了しました" + now_time.strftime('%Y/%m/%d %H:%M:%S') + "\n\n")

    return str(est_loss), str(n_vector_result)


if __name__ == '__main__':
    # コマンドラインからプログラムを動かす時のオプションを実装
    parser = argparse.ArgumentParser(description='Pytorch' + __file__)
    parser.add_argument('--epoch', '-e', type=int, default=d_EPOCH,
                        help='Number of sweeps over the dataset to train')
    parser.add_argument('--gpu', '-g', type=str, default=d_GPU,
                        help='if you want to use GPU, select cuda. cpu for cpu')
    parser.add_argument('--M', '-m', default=d_LATTICE,
                        help='number of lattice points')
    parser.add_argument('--N', '-n', default=d_PARTICLE,
                        help='number of particle')
    parser.add_argument('--U', '-u', default=d_U,
                        help='value of U')
    parser.add_argument('--J', '-j', default=d_J,
                        help='value of J')
    parser.add_argument('--out', '-o', default=d_OUTPUT_FILE_NAME,
                        help='output file name')
    args = parser.parse_args()

    EPOCH = args.epoch
    GPU = args.gpu
    LATTICE = args.M
    PARTICLE = args.N
    U = args.U
    J = args.J
    OUTPUT_FILE_NAME = args.out
    DEVICE = torch.device(GPU)

    result = learning()
    print("ene" + result[0])
    print("num" + result[1])
    """    
    aaa = MyModel()
    aaa.to(DEVICE)
    ddd = MyLoss(SAMPLE_NUM)
    ggg = optim.SGD(params=aaa.parameters(), lr=LR, momentum=MOMENTUM)
    start = time.time()
    bb1 = metropolis(SAMPLE_NUM, aaa)
    print("metro:{0}".format(time.time() - start) + "[sec]")
    start = time.time()
    bb2, bb3 = make_sample(bb1,  SAMPLE_NUM)
    print("make:{0}".format(time.time() - start) + "[sec]")
    start = time.time()
    cc1 = aaa(bb1)
    cc2 = aaa(bb2)
    cc3 = aaa(bb3)
    print("net:{0}".format(time.time() - start) + "[sec]")
    start = time.time()
    fff = ddd(bb1, cc1, cc2, cc3, SAMPLE_NUM)
    print("loss:{0}".format(time.time() - start) + "[sec]")
    start = time.time()
    fff.backward()
    print("backward:{0}".format(time.time() - start) + "[sec]")
    start = time.time()
    ggg.step()
    print("optim:{0}".format(time.time() - start) + "[sec]")
    print(fff)
    """
