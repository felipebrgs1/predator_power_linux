obj-m := src/predator_power.o

KERNELDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Sign the kernel module when Ubuntu/MOK keys are available.
KEY := /var/lib/shim-signed/mok/MOK.priv
X509 := /var/lib/shim-signed/mok/MOK.der

all: default

default:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules
	if [ -f "$(KEY)" ] && [ -f "$(X509)" ]; then \
		sudo kmodsign sha512 $(KEY) $(X509) src/predator_power.ko; \
	fi

clean:
	rm -rf src/*.o src/*~ src/.*.cmd src/*.ko src/*.mod src/*.mod.c \
		.tmp_versions modules.order Module.symvers
