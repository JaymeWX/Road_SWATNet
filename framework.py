import torch
import torch.nn as nn
from torch.autograd import Variable as V
from torch.optim import AdamW, Adam
import cv2
import numpy as np
from utils.scheduler_factory import create_scheduler

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

class ModelContainer():
    def __init__(self, net, loss, lr=2e-4, lr_end = 1e-6, epochs = 300, evalmode=False):
        self.net = net.cuda()
        # self.optimizer = Adam(params=self.net.parameters(), lr=lr)
        self.optimizer = AdamW(params=self.net.parameters(), lr=lr, weight_decay=0.02)
        # self.optimizer = torch.optim.RMSprop(params=self.net.parameters(), lr=lr)
        arg_sche ={'sched': 'cosine', 'epochs': epochs, 'min_lr': lr_end, 'decay_rate': 1, 'warmup_lr': 1e-6, 'warmup_epochs': 0, 'cooldown_epochs': 0}
        self.scheduler, _ = create_scheduler(AttrDict(arg_sche), self.optimizer)  
        self.loss = loss()
        self.old_lr = lr
        if evalmode:
            for i in self.net.modules():
                if isinstance(i, nn.BatchNorm2d):
                    i.eval()

    def set_input(self, img_batch, mask_batch=None, img_id=None):
        self.img = img_batch
        self.mask = mask_batch
        self.img_id = img_id

    def test_one_img(self, img):
        pred = self.net.forward(img)

        pred[pred > 0.5] = 1
        pred[pred <= 0.5] = 0

        mask = pred.squeeze().cpu().data.numpy()
        return mask

    def test_batch(self):
        self.forward(volatile=True)
        mask = self.net.forward(self.img).cpu().data.numpy().squeeze(1)
        mask[mask > 0.5] = 1
        mask[mask <= 0.5] = 0

        return mask, self.img_id

    def test_one_img_from_path(self, path):
        img = cv2.imread(path)
        img = np.array(img, np.float32) / 255.0 * 3.2 - 1.6
        img = V(torch.Tensor(img).cuda())

        mask = self.net.forward(img).squeeze().cpu().data.numpy()  # .squeeze(1)
        mask[mask > 0.5] = 1
        mask[mask <= 0.5] = 0

        return mask

    def forward(self, volatile=False):
        self.img = V(self.img.cuda(), volatile=volatile)
        if self.mask is not None:
            self.mask = V(self.mask.cuda(), volatile=volatile)

    def optimize(self):
        self.forward()
        self.optimizer.zero_grad()
        pred = self.net.forward(self.img)
        loss = self.loss(self.mask, pred)
        loss.backward()
        self.optimizer.step()
        return loss.data

    def save(self, path):
        torch.save(self.net.state_dict(), path)

    def load(self, path):
        state_dict = torch.load(path)
        self.net.load_state_dict(state_dict)

    def update_lr_by_scheduler(self, epoch):
        self.scheduler.step(epoch)

    def update_lr(self, new_lr, mylog, factor=False):
        if factor:
            new_lr = self.old_lr / new_lr
        for param_group in self.optimizer.param_groups:
            param_group['lr'] = new_lr

        print('update learning rate: %f -> %f' % (self.old_lr, new_lr), file=mylog)
        print('update learning rate: %f -> %f' % (self.old_lr, new_lr))
        self.old_lr = new_lr
