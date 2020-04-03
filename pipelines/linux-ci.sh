# before_install.sh

set -o xtrace

export NUMCORES=`grep -c ^processor /proc/cpuinfo`
if [ ! -n "$NUMCORES" ]; then
  export NUMCORES=`sysctl -n hw.ncpu`
fi
echo Using $NUMCORES cores

# Install dependencies
sudo apt-get update
APT_INSTALL_CMD='sudo apt-get install -y --no-install-recommends'
$APT_INSTALL_CMD dos2unix

function install_protobuf() {
    # Install protobuf
    local pb_dir="$HOME/.cache/pb"
    mkdir -p "$pb_dir"
    wget -qO- "https://github.com/google/protobuf/releases/download/v${PB_VERSION}/protobuf-${PB_VERSION}.tar.gz" | tar -xz -C "$pb_dir" --strip-components 1
    ccache -z
    cd "$pb_dir" && ./configure && make -j${NUMCORES} && make check && sudo make install && sudo ldconfig && cd -
    ccache -s
}

install_protobuf

# Update all existing python packages
pip install --quiet -U pip setuptools

pip list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1  | xargs -n1 pip install -U --quiet

# install.sh

script_path=$(python -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" "${BASH_SOURCE[0]}")
source "${script_path%/*}/setup.sh"

export ONNX_BUILD_TESTS=1
pip install --quiet protobuf numpy

export CMAKE_ARGS="-DONNX_WERROR=ON"
if [[ -n "USE_LITE_PROTO" ]]; then
    export CMAKE_ARGS="${CMAKE_ARGS} -DONNX_USE_LITE_PROTO=ON"
fi
export CMAKE_ARGS="${CMAKE_ARGS} -DONNXIFI_DUMMY_BACKEND=ON"
export ONNX_NAMESPACE=ONNX_NAMESPACE_FOO_BAR_FOR_CI

if [ "${ONNX_DEBUG}" == "1" ]; then
  export DEBUG=1
fi

time python setup.py --quiet bdist_wheel --universal --dist-dir .
find . -maxdepth 1 -name "*.whl" -ls -exec pip install {} \;

# script.sh

script_path=$(python -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" "${BASH_SOURCE[0]}")
source "${script_path%/*}/setup.sh"

# onnx c++ API tests
export LD_LIBRARY_PATH="${top_dir}/.setuptools-cmake-build/:$LD_LIBRARY_PATH"
# do not use find -exec here, it would ignore the segement fault of gtest.
./.setuptools-cmake-build/onnx_gtests
./.setuptools-cmake-build/onnxifi_test_driver_gtests onnx/backend/test/data/node

# onnx python API tests
pip install --quiet pytest nbval
pytest

# lint python code
pip install --quiet flake8
flake8

# Mypy only works with Python 3
if [ "${PYTHON_VERSION}" != "python2" ]; then
  # Mypy only works with our generated _pb.py files when we install in develop mode, so let's do that
  pip uninstall -y onnx
  time ONNX_NAMESPACE=ONNX_NAMESPACE_FOO_BAR_FOR_CI pip install --no-use-pep517 -e .[mypy]

  time python setup.py --quiet typecheck

  pip uninstall -y onnx
  rm -rf .setuptools-cmake-build
  time ONNX_NAMESPACE=ONNX_NAMESPACE_FOO_BAR_FOR_CI pip install .
fi

# check line endings to be UNIX
find . -type f -regextype posix-extended -regex '.*\.(py|cpp|md|h|cc|proto|proto3|in)' | xargs dos2unix --quiet
git status
git diff --exit-code

# check auto-gen files up-to-date
python onnx/defs/gen_doc.py
python onnx/gen_proto.py -l
python onnx/gen_proto.py -l --ml
python onnx/backend/test/stat_coverage.py
backend-test-tools generate-data
git status
git diff --exit-code

# Do not hardcode onnx's namespace in the c++ source code, so that
# other libraries who statically link with onnx can hide onnx symbols
# in a private namespace.
! grep -R --include='*.cc' --include='*.h' 'namespace onnx' .
! grep -R --include='*.cc' --include='*.h' 'onnx::' .

# results

script_path=$(python -c "import os; import sys; print(os.path.realpath(sys.argv[1]))" "${BASH_SOURCE[0]}")
source "${script_path%/*}/setup.sh"
